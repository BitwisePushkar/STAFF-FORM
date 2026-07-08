import re
from datetime import date, timedelta, datetime
from typing import Any
from django.utils import timezone
from rest_framework import serializers
from .models import StaffApplication, StaffApplicationDocument

PHONE_RE = re.compile(r"^\d{10}$")
EPF_UAN_RE = re.compile(r"^\d{12}$")
EPF_ACCOUNT_RE = re.compile(r"^[A-Z]{2}/[A-Z]{3,10}/\d{1,7}/\d{1,3}/\d{1,7}$")
EMAIL_RE = re.compile(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$")
HTML_TAG_RE = re.compile(r"<[^>]+>")
FILE_SIGNATURES = {
    b"\x25\x50\x44\x46": "application/pdf",
    b"\xff\xd8\xff": "image/jpeg",
    b"\x89\x50\x4e\x47": "image/png",
    b"RIFF": "image/webp",
    b"GIF8": "image/gif",
    b"\x49\x49\x2a\x00": "image/tiff",
    b"\x4d\x4d\x00\x2a": "image/tiff",
    b"\x00\x00\x01\x00": "image/x-icon",
    b"\x42\x4d": "image/bmp",
    b"\xd0\xcf\x11\xe0": "application/msword",
    b"\x50\x4b\x03\x04": "application/zip",
}
ALLOWED_IMAGE_EXTENSIONS = {
    ".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp",
    ".tiff", ".tif", ".svg", ".ico", ".heic", ".heif", ".avif",
}
ALLOWED_FILE_EXTENSIONS = {
    ".pdf",
    ".doc", ".docx",
    ".xls", ".xlsx",
    ".ppt", ".pptx",
    ".odt", ".ods", ".odp",
    ".txt", ".rtf", ".csv",
} | ALLOWED_IMAGE_EXTENSIONS
ALLOWED_MIME_TYPES = {
    "application/pdf",
    "image/jpeg",
    "image/png",
    "image/webp",
    "image/gif",
    "image/bmp",
    "image/tiff",
    "image/svg+xml",
    "image/x-icon",
    "image/vnd.microsoft.icon",
    "image/heic",
    "image/heif",
    "image/avif",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.ms-excel",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.ms-powerpoint",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "application/vnd.oasis.opendocument.text",
    "application/vnd.oasis.opendocument.spreadsheet",
    "application/vnd.oasis.opendocument.presentation",
    "text/plain",
    "text/csv",
    "application/rtf",
}
MAX_FILE_SIZE_MB = 5
MAX_FILE_SIZE_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024
VALID_DIVISIONS = {"First", "Second", "Third", "Pass", "Distinction", "Grade"}
MIN_AGE_YEARS = 18
MAX_AGE_YEARS = 65

EDUCATION_ATTACHMENT_MAP = {
    "attach_10th": {
        "10th", "10", "x", "ssc", "matric", "matriculation",
        "high school", "class 10", "class 10th", "secondary",
    },
    "attach_12th": {
        "12th", "12", "xii", "hsc", "intermediate",
        "senior secondary", "class 12", "class 12th",
    },
    "attach_diploma": {
        "diploma",
    },
    "attach_graduation": {
        "graduation", "bachelor", "b.tech", "btech", "b.e", "be",
        "b.sc", "bsc", "b.com", "bcom", "b.a", "ba", "bca", "bba",
        "b.arch", "b.pharm", "llb",
    },
    "attach_post_graduation": {
        "post graduation", "post-graduation", "postgraduation",
        "master", "m.tech", "mtech", "m.e", "me", "m.sc", "msc",
        "m.com", "mcom", "m.a", "ma", "mca", "mba", "m.arch",
        "m.pharm", "pg", "llm", "ph.d", "phd", "doctorate",
    },
}

ATTACHMENT_LABELS = {
    "attach_10th": "10th Marksheet",
    "attach_12th": "12th Marksheet",
    "attach_diploma": "Diploma certificate",
    "attach_graduation": "Graduation certificate",
    "attach_post_graduation": "Post Graduation certificate",
}

def _match_education_level(examination_name: str) -> set[str]:
    name = examination_name.lower().strip()
    matched = set()
    for attach_field, keywords in EDUCATION_ATTACHMENT_MAP.items():
        if any(kw in name for kw in keywords):
            matched.add(attach_field)
    return matched

def _is_blank(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    return False

def _strip_html(value: str) -> str:
    return HTML_TAG_RE.sub("", value)

def _calculate_age(dob: date, today: date) -> int:
    return today.year - dob.year - (
        (today.month, today.day) < (dob.month, dob.day)
    )

def _validate_file(value, field_label: str):
    if value is None:
        return value

    if not hasattr(value, "size"):
        return value

    name: str = getattr(value, "name", "") or ""

    if "." not in name:
        raise serializers.ValidationError(
            f"{field_label}: file must have an extension. "
            f"Allowed: {', '.join(sorted(ALLOWED_FILE_EXTENSIONS))}."
        )

    ext = "." + name.rsplit(".", 1)[-1].lower()

    if ext not in ALLOWED_FILE_EXTENSIONS:
        raise serializers.ValidationError(
            f"{field_label}: unsupported file type '{ext}'. "
            f"Allowed: {', '.join(sorted(ALLOWED_FILE_EXTENSIONS))}."
        )

    content_type = getattr(value, "content_type", None)
    if content_type and content_type not in ALLOWED_MIME_TYPES and content_type != "application/octet-stream":
        raise serializers.ValidationError(
            f"{field_label}: invalid content type '{content_type}'."
        )

    if value.size > MAX_FILE_SIZE_BYTES:
        raise serializers.ValidationError(
            f"{field_label}: file size must not exceed {MAX_FILE_SIZE_MB} MB "
            f"(uploaded: {value.size / (1024 * 1024):.1f} MB)."
        )

    pos = value.tell()
    header = value.read(8)
    value.seek(pos)
    if header:
        matched = any(header.startswith(sig) for sig in FILE_SIGNATURES)
        if not matched:
            raise serializers.ValidationError(
                f"{field_label}: file content does not match a supported format."
            )

    return value

def _validate_phone(value: str, field_label: str = "Phone number") -> str:
    value = value.strip()
    if not value:
        raise serializers.ValidationError(f"{field_label} is required.")
    if not PHONE_RE.match(value):
        raise serializers.ValidationError(
            f"{field_label} must be exactly 10 digits (digits only, no spaces or dashes)."
        )
    return value

def _validate_percentage(value: float, field_label: str = "Percentage") -> float:
    if not (0.0 <= value <= 100.0):
        raise serializers.ValidationError(
            f"{field_label} must be between 0.00 and 100.00."
        )
    return value

def _validate_year(value: int, field_label: str = "Year") -> int:
    current_year = timezone.now().year
    if not (1900 <= value <= current_year + 1):
        raise serializers.ValidationError(
            f"{field_label} must be between 1900 and {current_year + 1}."
        )
    return value

def _parse_date_string(value: Any, label: str) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    raw = str(value).strip()
    if not raw:
        raise serializers.ValidationError(f"{label} is required.")
    try:
        return date.fromisoformat(raw)
    except (ValueError, AttributeError):
        raise serializers.ValidationError(
            f"{label} must be a valid date in YYYY-MM-DD format."
        )

EDUCATION_REQUIRED_FIELDS = [
    "examination_name",
    "school_college",
    "board_university",
    "year_of_passing",
    "medium",
    "division",
    "percentage",
]

def _validate_education_entry(entry: Any, index: int) -> dict:
    prefix = f"education[{index}]"

    if not isinstance(entry, dict):
        raise serializers.ValidationError(
            {prefix: "Each education entry must be a JSON object."}
        )

    errors: dict = {}
    for field in EDUCATION_REQUIRED_FIELDS:
        val = entry.get(field)
        if val is None or (isinstance(val, str) and not val.strip()):
            errors[f"{prefix}.{field}"] = "This field is required."

    if errors:
        raise serializers.ValidationError(errors)

    try:
        year = int(entry["year_of_passing"])
    except (ValueError, TypeError):
        raise serializers.ValidationError(
            {f"{prefix}.year_of_passing": "Must be a valid integer year (e.g. 2010)."}
        )
    try:
        entry["year_of_passing"] = _validate_year(year, "Year of passing")
    except serializers.ValidationError as exc:
        raise serializers.ValidationError({f"{prefix}.year_of_passing": exc.detail})

    try:
        pct = float(entry["percentage"])
    except (ValueError, TypeError):
        raise serializers.ValidationError(
            {f"{prefix}.percentage": "Must be a valid number (e.g. 75.5)."}
        )
    try:
        entry["percentage"] = round(_validate_percentage(pct, "Percentage"), 2)
    except serializers.ValidationError as exc:
        raise serializers.ValidationError({f"{prefix}.percentage": exc.detail})

    division_raw: str = str(entry.get("division", "")).strip().title()
    if division_raw not in VALID_DIVISIONS:
        raise serializers.ValidationError(
            {
                f"{prefix}.division": (
                    f"'{division_raw}' is not a recognised division. "
                    f"Allowed values: {', '.join(sorted(VALID_DIVISIONS))}."
                )
            }
        )
    entry["division"] = division_raw

    for field in ("examination_name", "school_college", "board_university", "medium"):
        entry[field] = _strip_html(str(entry[field]).strip())
        if len(entry[field]) > 300:
            raise serializers.ValidationError(
                {f"{prefix}.{field}": "Must not exceed 300 characters."}
            )

    return entry

EXPERIENCE_REQUIRED_FIELDS = ("organization", "designation", "from_date", "to_date", "job_profile", "last_salary")

def _validate_experience_entry(entry: Any, index: int) -> dict:
    prefix = f"experience[{index}]"

    if not isinstance(entry, dict):
        raise serializers.ValidationError(
            {prefix: "Each experience entry must be a JSON object."}
        )

    errors: dict = {}
    for field in EXPERIENCE_REQUIRED_FIELDS:
        if _is_blank(entry.get(field)):
            errors[f"{prefix}.{field}"] = "This field is required."

    if errors:
        raise serializers.ValidationError(errors)

    try:
        from_date = _parse_date_string(entry["from_date"], "from_date")
    except serializers.ValidationError as exc:
        raise serializers.ValidationError({f"{prefix}.from_date": exc.detail})

    if from_date > timezone.now().date():
        raise serializers.ValidationError(
            {f"{prefix}.from_date": "from_date cannot be in the future."}
        )
    entry["from_date"] = from_date.isoformat()

    to_date_raw = entry.get("to_date")
    try:
        to_date = _parse_date_string(to_date_raw, "to_date")
    except serializers.ValidationError as exc:
        raise serializers.ValidationError({f"{prefix}.to_date": exc.detail})
    if to_date < from_date:
        raise serializers.ValidationError(
            {f"{prefix}.to_date": "to_date cannot be earlier than from_date."}
        )
    if to_date > timezone.now().date():
        raise serializers.ValidationError(
            {f"{prefix}.to_date": "to_date cannot be in the future."}
        )
    entry["to_date"] = to_date.isoformat() 

    for field in ("organization", "designation", "job_profile"):
        entry[field] = _strip_html(str(entry[field]).strip())
        if len(entry[field]) > 500:
            raise serializers.ValidationError(
                {f"{prefix}.{field}": "Must not exceed 500 characters."}
            )

    raw_salary = str(entry.get("last_salary") or "").strip()
    if not re.match(r"^\d{1,10}(\.\d{1,2})?$", raw_salary):
        raise serializers.ValidationError({
            f"{prefix}.last_salary": (
                "Salary must be a valid positive number with up to 2 decimal places "
                "(e.g. 50000 or 50000.50)."
            )
        })
    entry["last_salary"] = raw_salary

    return entry

def _validate_reference_entry(entry: Any, index: int) -> dict:
    prefix = f"references[{index}]"

    if not isinstance(entry, dict):
        raise serializers.ValidationError(
            {prefix: "Each reference entry must be a JSON object."}
        )

    errors: dict = {}
    for field in ("name", "address", "contact_number"):
        if _is_blank(entry.get(field)):
            errors[f"{prefix}.{field}"] = "This field is required."

    if errors:
        raise serializers.ValidationError(errors)

    contact = str(entry["contact_number"]).strip()
    if not PHONE_RE.match(contact):
        raise serializers.ValidationError(
            {f"{prefix}.contact_number": "Must be exactly 10 digits (digits only)."}
        )

    entry["name"] = _strip_html(str(entry["name"]).strip())
    if len(entry["name"]) > 200:
        raise serializers.ValidationError(
            {f"{prefix}.name": "Must not exceed 200 characters."}
        )

    entry["address"] = _strip_html(str(entry["address"]).strip())
    if len(entry["address"]) > 500:
        raise serializers.ValidationError(
            {f"{prefix}.address": "Must not exceed 500 characters."}
        )

    entry["contact_number"] = contact
    return entry

class StaffApplicationDocumentSerializer(serializers.ModelSerializer):
    class Meta:
        model = StaffApplicationDocument
        fields = "__all__"
        read_only_fields = ("uploaded_at", "application")

class StaffApplicationSerializer(serializers.ModelSerializer):
    additional_documents = StaffApplicationDocumentSerializer(many=True, read_only=True)
    full_name = serializers.SerializerMethodField()

    class Meta:
        model = StaffApplication
        fields = "__all__"
        read_only_fields = ("created_at", "updated_at", "full_name")

    def get_full_name(self, obj) -> str:
        return obj.full_name

    def validate_post_applied_for(self, value: str) -> str:
        value = value.strip()
        if not value:
            raise serializers.ValidationError("Post applied for cannot be blank.")
        if not re.match(r"^[A-Za-z\s\-\(\)']+$", value):
            raise serializers.ValidationError(
                "Post applied for must contain only letters, spaces, hyphens, "
                "apostrophes, or parentheses."
            )
        return value.title()

    def validate_surname(self, value: str) -> str:
        value = value.strip()
        if not value:
            raise serializers.ValidationError("Surname cannot be blank.")
        if not re.match(r"^[A-Za-z\s\-']+$", value):
            raise serializers.ValidationError(
                "Surname must contain only letters, spaces, hyphens, or apostrophes."
            )
        return value.title()

    def validate_first_name(self, value: str) -> str:
        value = value.strip()
        if not value:
            raise serializers.ValidationError("First name cannot be blank.")
        if not re.match(r"^[A-Za-z\s\-']+$", value):
            raise serializers.ValidationError(
                "First name must contain only letters, spaces, hyphens, or apostrophes."
            )
        return value.title()

    def validate_middle_name(self, value: str) -> str:
        value = value.strip()
        if value and not re.match(r"^[A-Za-z\s\-']+$", value):
            raise serializers.ValidationError(
                "Middle name must contain only letters, spaces, hyphens, or apostrophes."
            )
        return value.title() if value else ""

    def validate_father_name(self, value: str) -> str:
        value = value.strip()
        if not value:
            raise serializers.ValidationError("Father's name cannot be blank.")
        if not re.match(r"^[A-Za-z\s\-'.]+$", value):
            raise serializers.ValidationError(
                "Father's name must contain only letters, spaces, hyphens, or apostrophes."
            )
        return value.title()

    def validate_spouse_name(self, value: str) -> str:
        value = value.strip()
        if not value:
            return ""
        if not re.match(r"^[A-Za-z\s\-'.]+$", value):
            raise serializers.ValidationError(
                "Spouse name must contain only letters, spaces, hyphens, or apostrophes."
            )
        return value.title()

    def validate_mobile_number(self, value: str) -> str:
        value = _validate_phone(value, "Mobile number")
        qs = StaffApplication.objects.filter(mobile_number=value)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError(
                "An application with this mobile number already exists."
            )
        return value

    def validate_email(self, value: str) -> str:
        value = value.strip().lower()
        if not value:
            raise serializers.ValidationError("Email cannot be blank.")
        if not EMAIL_RE.match(value):
            raise serializers.ValidationError(
                "Enter a valid email address (e.g. name@example.com)."
            )
        qs = StaffApplication.objects.filter(email=value)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError(
                "An application with this email already exists."
            )
        return value

    def validate_dob(self, value: date) -> date:
        today = timezone.now().date()
        if value >= today:
            raise serializers.ValidationError(
                "Date of birth cannot be today or in the future."
            )
        age = _calculate_age(value, today)
        if age < MIN_AGE_YEARS:
            raise serializers.ValidationError(
                f"Applicant must be at least {MIN_AGE_YEARS} years old."
            )
        if age > MAX_AGE_YEARS:
            raise serializers.ValidationError(
                f"Date of birth seems incorrect — calculated age exceeds {MAX_AGE_YEARS} years."
            )
        return value

    def validate_correspondence_address_line1(self, value: str) -> str:
        value = _strip_html(value.strip())
        if not value:
            raise serializers.ValidationError(
                "Correspondence address line 1 cannot be blank."
            )
        return value

    def validate_correspondence_address_line2(self, value: str) -> str:
        return _strip_html(value.strip())

    def validate_permanent_address_line1(self, value: str) -> str:
        value = _strip_html(value.strip())
        if not value:
            raise serializers.ValidationError(
                "Permanent address line 1 cannot be blank."
            )
        return value

    def validate_permanent_address_line2(self, value: str) -> str:
        return _strip_html(value.strip())

    def validate_why_suitable(self, value: str) -> str:
        value = _strip_html(value.strip())
        if not value:
            raise serializers.ValidationError("This field cannot be blank.")
        if len(value) < 30:
            raise serializers.ValidationError(
                "Please provide a meaningful response (at least 30 characters)."
            )
        if len(value) > 5000:
            raise serializers.ValidationError(
                "Response must not exceed 5000 characters."
            )
        return value

    def validate_extra_curricular(self, value: str) -> str:
        value = _strip_html(value.strip())
        if len(value) > 3000:
            raise serializers.ValidationError(
                "Extra-curricular details must not exceed 3000 characters."
            )
        return value

    def validate_declaration_date(self, value):
        if value is None:
            return value
        today = timezone.now().date()
        if value > today:
            raise serializers.ValidationError(
                "Declaration date cannot be in the future."
            )
        if value < today - timedelta(days=30):
            raise serializers.ValidationError(
                "Declaration date must be within the last 30 days."
            )
        return value

    def validate_epf_number(self, value: str) -> str:
        value = value.strip().upper()
        if value and not (EPF_UAN_RE.match(value) or EPF_ACCOUNT_RE.match(value)):
            raise serializers.ValidationError(
                "EPF number must be a 12-digit UAN or a valid account number "
                "(e.g. MH/AKGEC/12345/123/1234567)."
            )
        return value

    def validate_marital_status(self, value: str) -> str:
        value = value.strip()
        allowed = {choice[0] for choice in StaffApplication.MARITAL_STATUS_CHOICES}
        if value not in allowed:
            raise serializers.ValidationError(
                f"Invalid marital status. Allowed values are: {', '.join(sorted(allowed))}."
            )
        return value

    def validate_category(self, value: str) -> str:
        value = value.strip()
        allowed = {choice[0] for choice in StaffApplication.CATEGORY_CHOICES}
        if value not in allowed:
            raise serializers.ValidationError(
                f"Invalid category. Allowed values are: {', '.join(sorted(allowed))}."
            )
        return value

    def validate_photograph(self, value):
        if value is None:
            return value
        _validate_file(value, "Photograph")
        if hasattr(value, "name") and value.name:
            ext = "." + value.name.rsplit(".", 1)[-1].lower()
            if ext not in ALLOWED_IMAGE_EXTENSIONS:
                raise serializers.ValidationError(
                    "Photograph must be a JPG or PNG image."
                )
        return value

    def validate_attach_10th(self, value):         return _validate_file(value, "10th attachment")
    def validate_attach_12th(self, value):         return _validate_file(value, "12th attachment")
    def validate_attach_diploma(self, value):      return _validate_file(value, "Diploma attachment")
    def validate_attach_graduation(self, value):   return _validate_file(value, "Graduation attachment")
    def validate_attach_post_graduation(self, v):  return _validate_file(v, "PG attachment")
    def validate_attach_pan_card(self, value):     return _validate_file(value, "PAN Card attachment")
    def validate_attach_aadhaar(self, value):      return _validate_file(value, "Aadhaar attachment")
    def validate_attach_form16(self, value):       return _validate_file(value, "Form 16 attachment")
    def validate_attach_last_salary(self, value):  return _validate_file(value, "Last Salary Certificate")
    def validate_attach_experience_certs(self, v): return _validate_file(v, "Experience Certificate")
    def validate_attach_fitness_cert(self, value): return _validate_file(value, "Fitness Certificate")
    def validate_attach_photos(self, value):       return _validate_file(value, "Photos attachment")

    def validate_education(self, value) -> list:
        if not isinstance(value, list):
            raise serializers.ValidationError(
                "Education must be provided as a JSON array."
            )
        if len(value) == 0:
            raise serializers.ValidationError(
                "At least one education entry is required."
            )
        if len(value) > 20:
            raise serializers.ValidationError("Maximum 20 education entries allowed.")
        return [_validate_education_entry(entry, i) for i, entry in enumerate(value)]

    def validate_experience(self, value) -> list:
        if value is None:
            return []
        if not isinstance(value, list):
            raise serializers.ValidationError(
                "Experience must be provided as a JSON array."
            )
        if len(value) > 20:
            raise serializers.ValidationError("Maximum 20 experience entries allowed.")
        return [_validate_experience_entry(entry, i) for i, entry in enumerate(value)]

    def validate_references(self, value) -> list:
        if value is None:
            return []
        if not isinstance(value, list):
            raise serializers.ValidationError(
                "References must be provided as a JSON array."
            )
        if len(value) > 5:
            raise serializers.ValidationError("A maximum of 5 references is allowed.")
        return [_validate_reference_entry(entry, i) for i, entry in enumerate(value)]

    def validate(self, data: dict) -> dict:
        instance = self.instance

        def _get(field, default=None):
            if field in data:
                return data[field]
            if instance is not None:
                return getattr(instance, field, default)
            return default

        marital_status   = _get("marital_status", "")
        date_of_marriage = _get("date_of_marriage")
        spouse_name      = _get("spouse_name", "")
        IS_MARRIED = marital_status == "Married"

        if IS_MARRIED and _is_blank(spouse_name):
            raise serializers.ValidationError({
                "spouse_name": "Spouse name is required for married applicants."
            })

        if not IS_MARRIED:
            data["spouse_name"] = ""
            data["date_of_marriage"] = None
            date_of_marriage = None

        if IS_MARRIED and not date_of_marriage:
            raise serializers.ValidationError({
                "date_of_marriage": "Date of marriage is required for married applicants."
            })

        if IS_MARRIED and date_of_marriage:
            today = timezone.now().date()

            if date_of_marriage > today:
                raise serializers.ValidationError({
                    "date_of_marriage": "Date of marriage cannot be in the future."
                })
            if date_of_marriage.year < 1950:
                raise serializers.ValidationError({
                    "date_of_marriage": "Marriage year cannot be before 1950."
                })

            dob = _get("dob")
            if dob:
                if date_of_marriage <= dob:
                    raise serializers.ValidationError({
                        "date_of_marriage": "Date of marriage must be after date of birth."
                    })
                years_at_marriage = (date_of_marriage - dob).days / 365.25
                if years_at_marriage < 18:
                    raise serializers.ValidationError({
                        "date_of_marriage": "Applicant was under 18 at the time of marriage."
                    })

        epf_member = _get("epf_member", False)
        epf_number = (_get("epf_number") or "").strip().upper()

        if epf_member and not epf_number:
            raise serializers.ValidationError({
                "epf_number": "EPF membership number is required when EPF Member is Yes."
            })
        if not epf_member:
            data["epf_number"] = ""

        declaration_accepted = _get("declaration_accepted", False)
        declaration_date     = _get("declaration_date")

        if not declaration_accepted:
            raise serializers.ValidationError({
                "declaration_accepted": (
                    "You must accept the declaration to submit the application."
                )
            })
        if declaration_accepted and not declaration_date:
            raise serializers.ValidationError({
                "declaration_date": (
                    "Declaration date is required when declaration is accepted."
                )
            })

        education = _get("education", [])

        if isinstance(education, list) and len(education) > 1:
            years = [
                int(e.get("year_of_passing"))
                for e in education
                if isinstance(e, dict)
                and str(e.get("year_of_passing", "")).lstrip("-").isdigit()
            ]
            if len(years) != len(set(years)):
                raise serializers.ValidationError({
                    "education": "Duplicate year_of_passing values are not allowed."
                })
            if years != sorted(years):
                raise serializers.ValidationError({
                    "education": (
                        "Education entries must be in chronological order (oldest first)."
                    )
                })

        if isinstance(education, list):
            required_attachments: set[str] = set()
            for entry in education:
                if isinstance(entry, dict) and entry.get("examination_name"):
                    required_attachments |= _match_education_level(str(entry["examination_name"]))

            missing = {}
            for attach_field in required_attachments:
                file_value = _get(attach_field)
                if not file_value:
                    label = ATTACHMENT_LABELS[attach_field]
                    missing[attach_field] = f"{label} upload is required based on your education entries."
            if missing:
                raise serializers.ValidationError(missing)

        experience = _get("experience", [])

        if isinstance(experience, list) and len(experience) > 1:
            intervals: list = []

            for exp in experience:
                if not isinstance(exp, dict):
                    continue
                fd_raw = exp.get("from_date")
                if not fd_raw:
                    continue
                try:
                    fd = date.fromisoformat(str(fd_raw))
                except (ValueError, TypeError):
                    continue

                td_raw = exp.get("to_date")
                td = (
                    date.fromisoformat(str(td_raw))
                    if td_raw
                    else date.max
                )
                intervals.append((fd, td))

            intervals.sort(key=lambda x: x[0])

            for i in range(len(intervals) - 1):
                start_a, end_a = intervals[i]
                start_b, _     = intervals[i + 1]

                if start_b <= end_a:
                    raise serializers.ValidationError({
                        "experience": (
                            "Two or more experience entries have overlapping date ranges. "
                            "Please review and correct the dates."
                        )
                    })

        return data