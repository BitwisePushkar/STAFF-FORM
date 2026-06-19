import csv
import json

from django.contrib import admin
from django.http import HttpResponse
from django.utils.html import format_html

from .models import StaffApplication, StaffApplicationDocument

class StaffApplicationDocumentInline(admin.TabularInline):
    model = StaffApplicationDocument
    extra = 1
    readonly_fields = ("uploaded_at",)

def export_applications_csv(modeladmin, request, queryset):
    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = 'attachment; filename="staff_applications.csv"'

    fields = [
        "id", "post_applied_for", "first_name", "middle_name", "surname",
        "father_name", "spouse_name", "category", "mobile_number", "email",
        "correspondence_address_line1", "correspondence_address_line2",
        "permanent_address_line1", "permanent_address_line2",
        "dob", "marital_status", "date_of_marriage",
        "education", "experience", "extra_curricular", "why_suitable",
        "epf_member", "epf_number", "references",
        "declaration_accepted", "declaration_date",
        "created_at", "updated_at",
    ]

    writer = csv.writer(response)
    writer.writerow(fields)

    for app in queryset.order_by("-created_at"):
        row = []
        for field in fields:
            value = getattr(app, field)
            if isinstance(value, (list, dict)):
                value = json.dumps(value, default=str)
            elif hasattr(value, "isoformat"):
                value = value.isoformat()
            row.append(value)
        writer.writerow(row)

    return response

export_applications_csv.short_description = "Download selected applications as CSV"


@admin.register(StaffApplication)
class StaffApplicationAdmin(admin.ModelAdmin):
    list_display = (
        "full_name_display",
        "post_applied_for",
        "email",
        "mobile_number",
        "category",
        "marital_status",
        "created_at",
    )
    search_fields = ("first_name", "surname", "email", "mobile_number", "post_applied_for")
    list_filter = ("post_applied_for", "category", "marital_status", "epf_member", "created_at")
    readonly_fields = ("created_at", "updated_at", "full_name_display")
    actions = [export_applications_csv]
    inlines = [StaffApplicationDocumentInline]

    fieldsets = (
        (
            "Basic Details",
            {
                "fields": (
                    "post_applied_for",
                    "surname",
                    "first_name",
                    "middle_name",
                    "father_name",
                    "spouse_name",
                    "category",
                    "photograph",
                )
            },
        ),
        (
            "Contact Details",
            {
                "fields": (
                    "correspondence_address_line1",
                    "correspondence_address_line2",
                    "permanent_address_line1",
                    "permanent_address_line2",
                    "mobile_number",
                    "email",
                )
            },
        ),
        (
            "Personal Details",
            {
                "fields": (
                    "dob",
                    "marital_status",
                    "date_of_marriage",
                )
            },
        ),
        (
            "Education",
            {
                "fields": ("education",),
                "description": (
                    "JSON array. Each entry: examination_name, school_college, "
                    "board_university, year_of_passing, medium, division, percentage."
                ),
            },
        ),
        (
            "Experience",
            {
                "fields": ("experience",),
                "description": (
                    "JSON array. Each entry: organization, designation, "
                    "from_date (YYYY-MM-DD), to_date, job_profile, last_salary."
                ),
            },
        ),
        (
            "Additional Information",
            {
                "fields": (
                    "extra_curricular",
                    "why_suitable",
                    "epf_member",
                    "epf_number",
                )
            },
        ),
        (
            "References",
            {
                "fields": ("references",),
                "description": "JSON array. Each entry: name, address, contact_number.",
            },
        ),
        (
            "Declaration",
            {
                "fields": (
                    "declaration_accepted",
                    "declaration_date",
                )
            },
        ),
        (
            "Attachments",
            {
                "fields": (
                    "attach_10th",
                    "attach_12th",
                    "attach_diploma",
                    "attach_graduation",
                    "attach_post_graduation",
                    "attach_pan_card",
                    "attach_aadhaar",
                    "attach_form16",
                    "attach_last_salary",
                    "attach_experience_certs",
                    "attach_fitness_cert",
                    "attach_photos",
                ),
                "classes": ("collapse",),
            },
        ),
        (
            "Meta",
            {
                "fields": ("created_at", "updated_at"),
                "classes": ("collapse",),
            },
        ),
    )

    @admin.display(description="Full Name")
    def full_name_display(self, obj: StaffApplication) -> str:
        return obj.full_name

@admin.register(StaffApplicationDocument)
class StaffApplicationDocumentAdmin(admin.ModelAdmin):
    list_display = ("application_name", "document_type", "file_link", "uploaded_at")
    list_filter = ("document_type", "uploaded_at")
    search_fields = (
        "application__first_name",
        "application__surname",
        "application__email",
    )
    readonly_fields = ("uploaded_at",)

    @admin.display(description="Applicant")
    def application_name(self, obj: StaffApplicationDocument) -> str:
        return obj.application.full_name

    @admin.display(description="File")
    def file_link(self, obj: StaffApplicationDocument) -> str:
        if obj.file:
            return format_html('<a href="{}" target="_blank">View</a>', obj.file.url)
        return "—"