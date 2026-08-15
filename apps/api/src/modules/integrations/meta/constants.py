"""Meta Marketing API constants.

The Graph API version is pinned in settings (META_GRAPH_API_VERSION) and
never silently downgraded. Permission set is intentionally minimal:
`ads_read` only — read-only access to ad accounts, campaigns, ad sets, ads
and insights. No mutation permission is ever requested.
"""

PROVIDER = "meta"

RESOURCE_TYPES = ("ad_accounts", "campaigns", "ad_sets", "ads", "insights")
INITIAL_RESOURCES = ("ad_accounts", "campaigns", "ad_sets", "ads", "insights")
INCREMENTAL_RESOURCES = ("campaigns", "ad_sets", "ads", "insights")

GRAPH_API_HOST = "graph.facebook.com"

# Ad account statuses (Marketing API ad-account reference).
ACCOUNT_STATUS_LABELS = {
    "1": "ACTIVE",
    "2": "DISABLED",
    "3": "UNSETTLED",
    "7": "PENDING_RISK_REVIEW",
    "8": "PENDING_SETTLEMENT",
    "9": "IN_GRACE_PERIOD",
    "100": "PENDING_CLOSURE",
    "101": "CLOSED",
    "201": "ANY_ACTIVE",
    "202": "ANY_CLOSED",
}

# Rate limit / throttling error codes (Marketing API error reference).
RATE_LIMIT_ERROR_CODES = {429, 613, 80004}
# OAuth token failures (190 = invalid/expired token, subcodes refine).
AUTH_ERROR_CODES = {190}
# Permission / authorization failures.
AUTHORIZATION_ERROR_CODES = {10, 101, 174, 200}
# Permanent errors that must not be retried indefinitely.
PERMANENT_ERROR_CODES = {2, 4, 17, 100, 368, 2500, 2635}

# Meta rejects insight time ranges longer than 37 months (error 3018).
MAX_INSIGHTS_RANGE_DAYS = 37 * 31

PAGE_SIZE = 100