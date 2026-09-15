-- =============================================================================
-- FINTECH GROWTH & REVENUE FUNNEL ANALYSIS
-- Goal: Measure volume, step conversion rates, and financial loss per stage
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
-- -----------------------------------------------------------------------------
WITH event_lags AS (
    SELECT
        user_id,
        event_name,
        event_timestamp,
        LAG(event_timestamp) OVER (
            PARTITION BY user_id
            ORDER BY event_timestamp
        ) AS prev_event_timestamp
    FROM user_events
)
SELECT
    event_name,
    ROUND(
        AVG(EXTRACT(EPOCH FROM (event_timestamp - prev_event_timestamp)) / 3600)::NUMERIC,
        2
    ) AS avg_hours_from_previous_step
FROM event_lags
WHERE prev_event_timestamp IS NOT NULL
GROUP BY event_name
ORDER BY avg_hours_from_previous_step DESC;
