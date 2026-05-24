from django.db import transaction, IntegrityError
from django.shortcuts import render, get_object_or_404
from django.contrib.admin.views.decorators import staff_member_required

from rest_framework import viewsets, status
from rest_framework.response import Response
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import AllowAny, IsAdminUser

from .models import StaffApplication, StaffApplicationDocument
from .serializers import StaffApplicationSerializer, _validate_file


# ------------------------------------------------------------------ #
#  Constants                                                           #
# ------------------------------------------------------------------ #

MAX_FILES_PER_TYPE = 10

# Must stay in sync with StaffApplicationDocument.DOCUMENT_TYPES keys
DOCUMENT_TYPE_KEYS = [
    "10th", "12th", "diploma", "graduation", "pg",
    "pan", "aadhaar", "form16", "salary",
    "experience", "fitness", "photo", "other",
]


# ------------------------------------------------------------------ #
#  ViewSet                                                             #
# ------------------------------------------------------------------ #

class StaffApplicationViewSet(viewsets.ModelViewSet):
    """
    CRUD endpoints for staff recruitment applications.

    Additional document uploads are accepted as multipart fields named
    `<doc_type>_files`  (e.g. `experience_files`, `photo_files`).
    Multiple files of the same type are supported up to MAX_FILES_PER_TYPE.

    File validation and count checks happen BEFORE any DB write or file
    storage write, so a validation failure never leaves orphaned files.
    """

    queryset = StaffApplication.objects.prefetch_related("additional_documents").all()
    serializer_class = StaffApplicationSerializer

    # ---------------------------------------------------------------- #
    #  Permissions                                                      #
    # ---------------------------------------------------------------- #
    #
    #  Action → permission mapping:
    #
    #    create          (POST   /applications/)          → AllowAny
    #                    Public form submission; anyone can apply.
    #
    #    list            (GET    /applications/)          → IsAdminUser
    #    retrieve        (GET    /applications/<id>/)     → IsAdminUser
    #    update          (PUT    /applications/<id>/)     → IsAdminUser
    #    partial_update  (PATCH  /applications/<id>/)     → IsAdminUser
    #    destroy         (DELETE /applications/<id>/)     → IsAdminUser
    #
    def get_permissions(self):
        if self.action == "create":
            return [AllowAny()]
        return [IsAdminUser()]

    # ---------------------------------------------------------------- #
    #  Create                                                           #
    # ---------------------------------------------------------------- #

    @transaction.atomic
    def create(self, request, *args, **kwargs):
        # Step 1 — validate additional documents BEFORE touching the DB or storage
        validated_docs = self._validate_additional_documents(request)

        # Step 2 — validate and save the main application
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            application = serializer.save()
        except IntegrityError:
            raise ValidationError({"detail": "Mobile number or email already exists."})

        # Step 3 — persist additional documents (already validated; no rollback risk)
        self._persist_additional_documents(application, validated_docs, replace=False)
        application.refresh_from_db()

        return Response(
            self.get_serializer(application).data,
            status=status.HTTP_201_CREATED,
            headers=self.get_success_headers(serializer.data),
        )

    # ---------------------------------------------------------------- #
    #  Update (PUT / PATCH)                                             #
    # ---------------------------------------------------------------- #

    @transaction.atomic
    def update(self, request, *args, **kwargs):
        partial = kwargs.pop("partial", False)
        instance = self.get_object()

        # Step 1 — validate additional documents BEFORE touching the DB or storage
        validated_docs = self._validate_additional_documents(request)

        # Step 2 — validate and save the main application
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)

        try:
            application = serializer.save()
        except IntegrityError:
            raise ValidationError({"detail": "Mobile number or email already exists."})

        # Step 3 — replace existing docs of each supplied type, save new files
        self._persist_additional_documents(application, validated_docs, replace=True)
        application.refresh_from_db()

        return Response(self.get_serializer(application).data)

    # ---------------------------------------------------------------- #
    #  Private helpers                                                  #
    # ---------------------------------------------------------------- #

    @staticmethod
    def _validate_additional_documents(request) -> dict[str, list]:
        """
        Runs ALL validation on incoming additional-document files and returns
        a clean  {doc_type: [file, ...]}  dict.

        Raises ValidationError immediately if anything is wrong.
        No files are written to storage at this stage.
        """
        errors = {}
        validated: dict[str, list] = {}

        for doc_type in DOCUMENT_TYPE_KEYS:
            files = request.FILES.getlist(f"{doc_type}_files")

            if not files:
                continue

            # Count check
            if len(files) > MAX_FILES_PER_TYPE:
                errors[f"{doc_type}_files"] = (
                    f"Maximum {MAX_FILES_PER_TYPE} files allowed per document type."
                )
                continue

            # Per-file extension / MIME / size check
            type_errors = []
            clean_files = []
            for i, f in enumerate(files):
                try:
                    _validate_file(f, f"{doc_type}[{i}]")
                    clean_files.append(f)
                except Exception as exc:
                    type_errors.append(str(exc))

            if type_errors:
                errors[f"{doc_type}_files"] = type_errors
            else:
                validated[doc_type] = clean_files

        if errors:
            raise ValidationError(errors)

        return validated

    @staticmethod
    def _persist_additional_documents(
        application: StaffApplication,
        validated_docs: dict[str, list],
        replace: bool,
    ) -> None:
        """
        Writes validated files to storage and creates DB records.

        If `replace=True` (update flow), existing records for each supplied
        doc_type are deleted (and their storage files removed) before the new
        ones are written — preventing stale files from accumulating.

        Called only after serializer.save() succeeds, so the transaction is
        already consistent and any IntegrityError has already been caught.
        """
        for doc_type, files in validated_docs.items():
            if replace:
                existing = StaffApplicationDocument.objects.filter(
                    application=application,
                    document_type=doc_type,
                )
                for doc in existing:
                    doc.file.delete(save=False)  # remove from disk / S3
                existing.delete()

            for uploaded_file in files:
                StaffApplicationDocument.objects.create(
                    application=application,
                    document_type=doc_type,
                    file=uploaded_file,
                )


# ------------------------------------------------------------------ #
#  Template views (staff-only)                                         #
# ------------------------------------------------------------------ #

@staff_member_required
def application_list_view(request):
    applications = StaffApplication.objects.order_by("-created_at")
    return render(
        request,
        "recruitment/list.html",
        {"applications": applications},
    )


@staff_member_required
def application_detail_view(request, pk: int):
    application = get_object_or_404(StaffApplication, pk=pk)
    docs = application.additional_documents.all()

    attachment_fields = [
        ("attach_10th",             "10th Marksheet + Certificate"),
        ("attach_12th",             "12th Marksheet + Certificate"),
        ("attach_diploma",          "Diploma Marksheets + Certificate"),
        ("attach_graduation",       "Graduation Marksheets + Degree"),
        ("attach_post_graduation",  "Post Graduation Marksheets + Degree"),
        ("attach_pan_card",         "PAN Card"),
        ("attach_aadhaar",          "Aadhaar Card"),
        ("attach_form16",           "Form 16"),
        ("attach_last_salary",      "Last Salary Certificate"),
        ("attach_experience_certs", "Experience Certificates"),
        ("attach_fitness_cert",     "Fitness Certificate"),
        ("attach_photos",           "Latest Photos"),
    ]
    attachments = [
        (label, getattr(application, field_name))
        for field_name, label in attachment_fields
    ]

    return render(
        request,
        "recruitment/detail.html",
        {
            "application": application,
            "docs": docs,
            "attachments": attachments,
        },
    )