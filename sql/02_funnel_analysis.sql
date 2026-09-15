-- =============================================================================
-- FINTECH GROWTH & REVENUE FUNNEL ANALYSIS
-- Goal: Measure volume, step conversion rates, financial loss, cohorts & channels
-- =============================================================================

-- -----------------------------------------------------------------------------
-- 1. Overall funnel (volume and step-by-step conversion)
-- -----------------------------------------------------------------------------
WITH funnel_stages AS (
    SELECT
        e.user_id,
        MAX(CASE WHEN e.event_name = 'account_created' THEN 1 ELSE 0 END) AS stage_1_signup,
        MAX(CASE WHEN e.event_name = 'document_uploaded' THEN 1 ELSE 0 END) AS stage_2_doc_upload,
        MAX(CASE WHEN e.event_name = 'kyc_approved' THEN 1 ELSE 0 END) AS stage_3_kyc_approved,
        MAX(CASE WHEN e.event_name = 'first_deposit_initiated' THEN 1 ELSE 0 END) AS stage_4_first_deposit
    FROM user_events e
    GROUP BY e.user_id
),
aggregated_funnel AS (
    SELECT
        COUNT(user_id) AS total_signups,
        SUM(stage_1_signup) AS users_created_account,
        SUM(stage_2_doc_upload) AS users_uploaded_doc,
        SUM(stage_3_kyc_approved) AS users_kyc_approved,
        SUM(stage_4_first_deposit) AS users_first_deposit
    FROM funnel_stages
)
SELECT
    total_signups,
    users_uploaded_doc,
    ROUND((users_uploaded_doc::NUMERIC / NULLIF(total_signups, 0)) * 100, 2) AS pct_signup_to_doc,
    users_kyc_approved,
    -- Critical bottleneck: KYC verification drop-off
    ROUND((users_kyc_approved::NUMERIC / NULLIF(users_uploaded_doc, 0)) * 100, 2) AS pct_doc_to_kyc,
    users_first_deposit,
    ROUND((users_first_deposit::NUMERIC / NULLIF(users_kyc_approved, 0)) * 100, 2) AS pct_kyc_to_deposit,
    ROUND((users_first_deposit::NUMERIC / NULLIF(total_signups, 0)) * 100, 2) AS overall_conversion_rate
FROM aggregated_funnel;


-- -----------------------------------------------------------------------------
-- 2. Financial impact of KYC drop-off (estimated lost deposit volume)
-- -----------------------------------------------------------------------------
WITH user_deposits AS (
    SELECT
        user_id,
        SUM(amount) AS total_deposited
    FROM financial_transactions
    WHERE transaction_type = 'deposit'
      AND status = 'completed'
    GROUP BY user_id
),
avg_revenue_per_converted_user AS (
    SELECT
        AVG(total_deposited) AS avg_deposit_val
    FROM user_deposits
),
lost_users AS (
    SELECT
        COUNT(DISTINCT user_id) AS lost_at_kyc_count
    FROM user_events
    WHERE user_id IN (
        SELECT user_id FROM user_events WHERE event_name = 'document_uploaded'
    )
      AND user_id NOT IN (
        SELECT user_id FROM user_events WHERE event_name = 'kyc_approved'
    )
)
SELECT
    lu.lost_at_kyc_count AS users_stuck_at_kyc,
    ROUND(ar.avg_deposit_val, 2) AS avg_deposit_per_active_user,
    ROUND(lu.lost_at_kyc_count * ar.avg_deposit_val, 2) AS estimated_lost_revenue_volume
FROM lost_users lu
CROSS JOIN avg_revenue_per_converted_user ar;


-- -----------------------------------------------------------------------------
-- 3. Average conversion time (time-to-value in hours between consecutive events)
-- Uses LAG() to measure stage-to-stage latency per user
-- -----------------------------------------------------------------------------
WITH event_lags AS (
    SELECT
        user_id,
        event_name,
        event_timestamp,
        LAG(event_timestamp) OVER (
            PARTITION BY user_id
            ORDER BY event_timestamp
        ) AS prev_event_timestamp,
        LEAD(event_timestamp) OVER (
            PARTITION BY user_id
            ORDER BY event_timestamp
        ) AS next_event_timestamp,
        FIRST_VALUE(event_timestamp) OVER (
            PARTITION BY user_id
            ORDER BY event_timestamp
            ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING
        ) AS journey_start_ts
    FROM user_events
)
SELECT
    event_name,
    ROUND(
        AVG(EXTRACT(EPOCH FROM (event_timestamp - prev_event_timestamp)) / 3600)::NUMERIC,
        2
    ) AS avg_hours_from_previous_step,
    ROUND(
        AVG(EXTRACT(EPOCH FROM (event_timestamp - journey_start_ts)) / 3600)::NUMERIC,
        2
    ) AS avg_hours_from_signup
FROM event_lags
WHERE prev_event_timestamp IS NOT NULL
GROUP BY event_name
ORDER BY avg_hours_from_previous_step DESC;


-- -----------------------------------------------------------------------------
-- 4. Cohort analysis — KYC conversion by signup month (safra)
-- Uses LAG / LEAD / FIRST_VALUE to track MoM KYC health vs baseline cohort
-- -----------------------------------------------------------------------------
WITH user_funnel AS (
    SELECT
        u.user_id,
        DATE_TRUNC('month', u.signup_timestamp)::DATE AS cohort_month,
        MAX(CASE WHEN e.event_name = 'document_uploaded' THEN 1 ELSE 0 END) AS uploaded_doc,
        MAX(CASE WHEN e.event_name = 'kyc_approved' THEN 1 ELSE 0 END) AS kyc_approved
    FROM users u
    LEFT JOIN user_events e ON e.user_id = u.user_id
    GROUP BY u.user_id, DATE_TRUNC('month', u.signup_timestamp)::DATE
),
cohort_metrics AS (
    SELECT
        cohort_month,
        COUNT(*) AS cohort_signups,
        SUM(uploaded_doc) AS users_uploaded_doc,
        SUM(kyc_approved) AS users_kyc_approved,
        ROUND(
            (SUM(kyc_approved)::NUMERIC / NULLIF(SUM(uploaded_doc), 0)) * 100,
            2
        ) AS kyc_conversion_rate
    FROM user_funnel
    GROUP BY cohort_month
)
SELECT
    cohort_month,
    cohort_signups,
    users_uploaded_doc,
    users_kyc_approved,
    kyc_conversion_rate,
    LAG(kyc_conversion_rate) OVER (ORDER BY cohort_month) AS prev_month_kyc_rate,
    LEAD(kyc_conversion_rate) OVER (ORDER BY cohort_month) AS next_month_kyc_rate,
    FIRST_VALUE(kyc_conversion_rate) OVER (
        ORDER BY cohort_month
        ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING
    ) AS baseline_first_cohort_rate,
    ROUND(
        kyc_conversion_rate
        - LAG(kyc_conversion_rate) OVER (ORDER BY cohort_month),
        2
    ) AS mom_change_pp,
    ROUND(
        kyc_conversion_rate
        - FIRST_VALUE(kyc_conversion_rate) OVER (
            ORDER BY cohort_month
            ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING
        ),
        2
    ) AS vs_baseline_pp
FROM cohort_metrics
ORDER BY cohort_month;


-- -----------------------------------------------------------------------------
-- 5. Acquisition vs conversion — funnel retention by acquisition_channel
-- Uses window functions to benchmark each channel against the best performer
-- -----------------------------------------------------------------------------
WITH user_funnel AS (
    SELECT
        u.user_id,
        u.acquisition_channel,
        MAX(CASE WHEN e.event_name = 'account_created' THEN 1 ELSE 0 END) AS signup,
        MAX(CASE WHEN e.event_name = 'document_uploaded' THEN 1 ELSE 0 END) AS uploaded_doc,
        MAX(CASE WHEN e.event_name = 'kyc_approved' THEN 1 ELSE 0 END) AS kyc_approved,
        MAX(CASE WHEN e.event_name = 'first_deposit_initiated' THEN 1 ELSE 0 END) AS first_deposit
    FROM users u
    LEFT JOIN user_events e ON e.user_id = u.user_id
    GROUP BY u.user_id, u.acquisition_channel
),
channel_metrics AS (
    SELECT
        acquisition_channel,
        COUNT(*) AS signups,
        SUM(uploaded_doc) AS users_uploaded_doc,
        SUM(kyc_approved) AS users_kyc_approved,
        SUM(first_deposit) AS users_first_deposit,
        SUM(uploaded_doc) - SUM(kyc_approved) AS users_lost_at_kyc,
        ROUND((SUM(uploaded_doc)::NUMERIC / NULLIF(COUNT(*), 0)) * 100, 2) AS pct_signup_to_doc,
        ROUND((SUM(kyc_approved)::NUMERIC / NULLIF(SUM(uploaded_doc), 0)) * 100, 2) AS pct_doc_to_kyc,
        ROUND((SUM(first_deposit)::NUMERIC / NULLIF(SUM(kyc_approved), 0)) * 100, 2) AS pct_kyc_to_deposit,
        ROUND((SUM(first_deposit)::NUMERIC / NULLIF(COUNT(*), 0)) * 100, 2) AS overall_conversion_rate,
        ROUND(
            ((SUM(uploaded_doc) - SUM(kyc_approved))::NUMERIC / NULLIF(SUM(uploaded_doc), 0)) * 100,
            2
        ) AS kyc_dropoff_rate
    FROM user_funnel
    GROUP BY acquisition_channel
)
SELECT
    acquisition_channel,
    signups,
    users_uploaded_doc,
    users_kyc_approved,
    users_first_deposit,
    users_lost_at_kyc,
    pct_signup_to_doc,
    pct_doc_to_kyc,
    pct_kyc_to_deposit,
    overall_conversion_rate,
    kyc_dropoff_rate,
    FIRST_VALUE(acquisition_channel) OVER (
        ORDER BY overall_conversion_rate DESC
        ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING
    ) AS best_converting_channel,
    FIRST_VALUE(overall_conversion_rate) OVER (
        ORDER BY overall_conversion_rate DESC
        ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING
    ) AS best_channel_conversion_rate,
    ROUND(
        overall_conversion_rate
        - FIRST_VALUE(overall_conversion_rate) OVER (
            ORDER BY overall_conversion_rate DESC
            ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING
        ),
        2
    ) AS gap_vs_best_channel_pp,
    LAG(overall_conversion_rate) OVER (ORDER BY overall_conversion_rate DESC) AS next_best_conversion_rate,
    LEAD(overall_conversion_rate) OVER (ORDER BY overall_conversion_rate DESC) AS following_channel_rate
FROM channel_metrics
ORDER BY overall_conversion_rate DESC;
