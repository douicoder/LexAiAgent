SUGGESTIONS = [
    "My landlord is not returning my security deposit after I vacated",
    "I have a property registration issue with unclear title documents",
    "I need to evict a tenant who has not paid rent for 3 months",
    "I need a legal notice for a property dispute",
    "I want to understand my legal rights as a tenant in India",
]

SEVERITY_COLORS = {
    "low": "badge-success",
    "medium": "badge-warning",
    "high": "badge-error",
    "urgent": "badge-error",
}

STATUS_LABELS = {
    "processing": "Processing",
    "analyzed": "Analyzed",
    "notice_generated": "Notice Ready",
    "closed": "Closed",
}

CASE_TYPE_LABELS = {
    "tenancy_dispute": "Tenancy Dispute",
    "property_ownership": "Property Ownership",
    "property_registration": "Property Registration",
    "other": "Other",
}

LOADING_STEPS = [
    "Analyzing case...",
    "Searching laws...",
    "Preparing recommendations...",
    "Drafting legal notice...",
]
