from django.db import models
from django.core.validators import RegexValidator, MinValueValidator, MaxValueValidator

phone_validator = RegexValidator(
    regex=r'^\d{10}$',
    message="Phone number must be exactly 10 digits.",
)

class StaffApplication(models.Model):
    post_applied_for = models.CharField(max_length=200)
    surname = models.CharField(max_length=100)
    first_name = models.CharField(max_length=100)
    middle_name = models.CharField(max_length=100, blank=True, default="")
    father_name = models.CharField(max_length=200)
    spouse_name = models.CharField(max_length=200, blank=True, default="")
    CATEGORY_CHOICES = [
        ("General", "General"),
        ("OBC", "OBC"),
        ("SC", "SC"),
        ("ST", "ST"),
    ]
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES)
    photograph = models.FileField(upload_to="photographs/", null=False, blank=False)
    correspondence_address_line1 = models.CharField(max_length=300)
    correspondence_address_line2 = models.CharField(max_length=300, blank=True, default="")
    permanent_address_line1 = models.CharField(max_length=300)
    permanent_address_line2 = models.CharField(max_length=300, blank=True, default="")
    mobile_number = models.CharField(max_length=10, unique=True, validators=[phone_validator])
    email = models.EmailField(unique=True)
    dob = models.DateField()
    MARITAL_STATUS_CHOICES = [
        ("Single", "Single"),
        ("Married", "Married"),
        ("Divorced", "Divorced"),
        ("Widowed", "Widowed"),
        ("Separated", "Separated"),
    ]
    marital_status = models.CharField(max_length=20, choices=MARITAL_STATUS_CHOICES)
    date_of_marriage = models.DateField(null=True, blank=True)
    education = models.JSONField(default=list, blank=True)
    experience = models.JSONField(default=list, blank=True)
    extra_curricular = models.TextField(blank=True, default="")
    why_suitable = models.TextField()
    epf_member = models.BooleanField(default=False)
    epf_number = models.CharField(max_length=22, blank=True, default="")
    references = models.JSONField(default=list, blank=True)
    declaration_accepted = models.BooleanField(default=False)
    declaration_date = models.DateField(null=True, blank=True)
    attach_10th = models.FileField(upload_to="attachments/10th/", null=True, blank=True)
    attach_12th = models.FileField(upload_to="attachments/12th/", null=True, blank=True)
    attach_diploma = models.FileField(upload_to="attachments/diploma/", null=True, blank=True)
    attach_graduation = models.FileField(upload_to="attachments/graduation/", null=True, blank=True)
    attach_post_graduation = models.FileField(upload_to="attachments/pg/", null=True, blank=True)
    attach_pan_card = models.FileField(upload_to="attachments/pan/", null=True, blank=True)
    attach_aadhaar = models.FileField(upload_to="attachments/aadhaar/", null=True, blank=True)
    attach_form16 = models.FileField(upload_to="attachments/form16/", null=True, blank=True)
    attach_last_salary = models.FileField(upload_to="attachments/salary/", null=True, blank=True)
    attach_experience_certs = models.FileField(upload_to="attachments/experience/", null=True, blank=True)
    attach_fitness_cert = models.FileField(upload_to="attachments/fitness/", null=True, blank=True)
    attach_photos = models.FileField(upload_to="attachments/photos/", null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Staff Application"
        verbose_name_plural = "Staff Applications"

    def __str__(self) -> str:
        return f"{self.full_name} – {self.post_applied_for}"

    @property
    def full_name(self) -> str:
        parts = filter(None, [self.first_name, self.middle_name, self.surname])
        return " ".join(parts)

class StaffApplicationDocument(models.Model):
    DOCUMENT_TYPES = [
        ("10th", "10th Marksheet + Certificate"),
        ("12th", "12th Marksheet + Certificate"),
        ("diploma", "Diploma Marksheets + Certificate"),
        ("graduation", "Graduation Marksheets + Degree"),
        ("pg", "Post Graduation Marksheets + Degree"),
        ("pan", "PAN Card"),
        ("aadhaar", "Aadhaar Card"),
        ("form16", "Form 16"),
        ("salary", "Last Salary Certificate"),
        ("experience", "Experience Certificate"),
        ("fitness", "Fitness Certificate"),
        ("photo", "Latest Photo"),
        ("other", "Other"),
    ]

    application = models.ForeignKey(
        StaffApplication,
        related_name="additional_documents",
        on_delete=models.CASCADE,
    )
    document_type = models.CharField(max_length=20, choices=DOCUMENT_TYPES)
    file = models.FileField(upload_to="additional_docs/")
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["document_type", "uploaded_at"]
        verbose_name = "Staff Application Document"
        verbose_name_plural = "Staff Application Documents"

    def __str__(self) -> str:
        return f"{self.application.full_name} – {self.get_document_type_display()}"