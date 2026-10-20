"""Domain rules that do not depend on the screens or storage."""

from datetime import date, datetime, timedelta

# Roles
RECIPIENT = "recipient"
VOLUNTEER = "volunteer"
STAFF = "staff"
MANAGER = "manager"
ADMIN = "admin"

INTERNAL_ROLES = (VOLUNTEER, STAFF, MANAGER, ADMIN)
ROLE_LABELS = {
    RECIPIENT: "Recipient",
    VOLUNTEER: "Volunteer",
    STAFF: "Organisation Staff",
    MANAGER: "Organisation Manager",
    ADMIN: "IT Admin",
}

# Which role may create or deactivate which account type (FR-04, FR-05, FR-07)
MANAGEABLE_ROLES = {
    ADMIN: (MANAGER,),
    MANAGER: (STAFF, VOLUNTEER),
}

NEAR_EXPIRY_DAYS = 7

# Sign-in rules (NFR-09)
PASSWORD_MIN_LENGTH = 15
PASSWORD_MAX_LENGTH = 128
FREE_LOGIN_ATTEMPTS = 5        # after this many wrong passwords in a row, a pause starts
LOCK_FIRST_MINUTES = 1         # the pause doubles with each further wrong password ...
LOCK_MAX_MINUTES = 15          # ... up to this long, so nobody is locked out for good
SESSION_IDLE_MINUTES = 15
SESSION_MAX_HOURS = 8

# Statuses
SCHEDULED = "Scheduled"
COLLECTED = "Collected"
ALLOCATED = "Allocated"
CANCELLED = "Cancelled"
NO_SHOW = "No-show"
PENDING = "Pending"
APPROVED = "Approved"
DECLINED = "Declined"
WITHDRAWN = "Withdrawn"
EXPIRED = "Expired"            # swap request still waiting when the pickup window ended
CLOSED = "Closed"              # swap request still waiting when the food was collected

# Check-in queue (FR-50 to FR-55)
WAITING = "Waiting"
SERVING = "Serving"
CHECK_IN_EARLY_MINUTES = 60    # Recipients can check in up to an hour before their time

# Audit log categories (FR-56, FR-57): IT Admins read security, Managers read operations
SECURITY = "Security"
OPERATIONS = "Operations"

# Quick reasons a Recipient can tap when asking for a swap. Always optional.
SWAP_REASON_CHIPS = (
    "I can't eat this",
    "I have no way to cook it",
    "I already have enough",
    "My family won't eat it",
)

# Anonymous feedback box
FEEDBACK_CATEGORIES = (
    "General",
    "Food quality",
    "Pickup and waiting",
    "Staff and volunteers",
    "Using this website",
)
FEEDBACK_RATINGS = {
    1: ("\U0001F61E", "Poor"),
    2: ("\U0001F641", "Not great"),
    3: ("\U0001F610", "Okay"),
    4: ("\U0001F642", "Good"),
    5: ("\U0001F604", "Great"),
}
FEEDBACK_MAX_LENGTH = 500
FEEDBACK_PER_SESSION = 5       # per browser session, kept in memory only (FR-49)
FEEDBACK_KEEP_DAYS = 90

TASK_TYPES = ("Receiving", "Distribution")

# Profile fields: (key, label, required, why we ask) for FR-18
PROFILE_FIELDS = [
    ("household_size", "Household size", True,
     "Helps us prepare enough food for everyone in your home."),
    ("allergies", "Allergies", False,
     "So we never give you food that could make someone unwell. Separate with commas."),
    ("dietary_restrictions", "Dietary restrictions", False,
     "For example vegetarian or gluten free. Separate with commas."),
    ("cultural_needs", "Cultural or religious food needs", False,
     "For example halal or kosher. Separate with commas."),
    ("accessibility_needs", "Accessibility needs", False,
     "Anything that would make pickup easier for you."),
    ("preferred_pickup", "Preferred pickup times", False,
     "So we can suggest a time that suits you."),
    ("urgency", "Urgency", False,
     "Lets staff know if you need support soon. Staff make every decision themselves."),
]

URGENCY_LEVELS = ("Standard", "Soon", "Urgent")


class DomainError(Exception):
    """A rule was broken; the message is shown to the user."""


class PermissionDenied(DomainError):
    """The signed-in role may not do this (FR-03, NFR-01)."""


class EditConflict(DomainError):
    """Someone else saved this record after the form was opened."""


def today():
    return date.today()


def now():
    return datetime.now()


def parse_date(value):
    if isinstance(value, date):
        return value
    try:
        return datetime.strptime(str(value), "%Y-%m-%d").date()
    except (TypeError, ValueError):
        raise DomainError("Please enter a date in the format YYYY-MM-DD.")


def parse_time(value):
    """Return minutes after midnight for an HH:MM time."""
    try:
        moment = datetime.strptime(str(value).strip()[:5], "%H:%M")
    except (TypeError, ValueError):
        raise DomainError("Please enter a time in the format HH:MM.")
    return moment.hour * 60 + moment.minute


def format_time(minutes):
    minutes = max(0, min(int(minutes), 23 * 60 + 59))
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def is_expired(batch, on=None):
    """FR-16: expired when the expiry date is earlier than today."""
    return parse_date(batch["expiry_date"]) < (on or today())


def is_near_expiry(batch, on=None):
    """FR-15: within the next seven calendar days, including the seventh."""
    on = on or today()
    expiry = parse_date(batch["expiry_date"])
    return on <= expiry <= on + timedelta(days=NEAR_EXPIRY_DAYS)


def expiry_label(batch, on=None):
    """Text status so nothing relies on colour alone (NFR-08)."""
    if is_expired(batch, on):
        return "Expired"
    if is_near_expiry(batch, on):
        return "Near expiry"
    return "OK"


def is_usable(batch, on=None):
    """Food that may be set aside or handed out: not expired and not on a safety hold."""
    return not is_expired(batch, on) and not batch.get("on_hold")


def pickup_start(allocation):
    """The booked pickup as a datetime."""
    minutes = parse_time(allocation["pickup_time"])
    return datetime.combine(parse_date(allocation["pickup_date"]), datetime.min.time()) \
        + timedelta(minutes=minutes)


def pickup_end(allocation, window_minutes):
    """When the pickup window closes: booked time plus the window length."""
    return pickup_start(allocation) + timedelta(minutes=window_minutes)


def split_list(value):
    if isinstance(value, list):
        items = value
    else:
        items = str(value or "").split(",")
    return [i.strip().lower() for i in items if i and i.strip()]


def suitability_problems(batch, profile):
    """Return reasons a batch is unsuitable for a recipient (FR-20, FR-35)."""
    if not profile:
        return []
    problems = []
    allergens = set(split_list(batch.get("allergens", [])))
    clash = allergens & set(split_list(profile.get("allergies", [])))
    if clash:
        problems.append("contains " + ", ".join(sorted(clash)))
    tags = set(split_list(batch.get("dietary_tags", [])))
    needs = split_list(profile.get("dietary_restrictions", [])) + split_list(
        profile.get("cultural_needs", []))
    missing = [n for n in needs if n not in tags]
    if missing:
        problems.append("not marked " + ", ".join(missing))
    return problems


def needs_summary(profile):
    """FR-19: only allocation-relevant details, no contact or personal notes."""
    if not profile:
        return None
    return {
        "household_size": profile.get("household_size"),
        "allergies": split_list(profile.get("allergies")),
        "dietary": split_list(profile.get("dietary_restrictions"))
        + split_list(profile.get("cultural_needs")),
        "urgency": profile.get("urgency") or "Standard",
    }
