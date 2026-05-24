from django.db import transaction, IntegrityError
from django.shortcuts import render, get_object_or_404
from django.contrib.admin.views.decorators import staff_member_required
from rest_framework import viewsets, status
from rest_framework.response import Response
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import AllowAny, IsAdminUser
from .models import StaffApplication, StaffApplicationDocument
from .serializers import StaffApplicationSerializer, _validate_file

MAX_FILES_PER_TYPE = 10

DOCUMENT_TYPE_KEYS = [
    "10th", "12th", "diploma", "graduation", "pg",
    "pan", "aadhaar", "form16", "salary",
    "experience", "fitness", "photo", "other",
]

class StaffApplicationViewSet(viewsets.ModelViewSet):
    queryset = StaffApplication.objects.prefetch_related("additional_documents").all()
    serializer_class = StaffApplicationSerializer
    def get_permissions(self):
        if self.action == "create":
            return [AllowAny()]
        return [IsAdminUser()]

    @transaction.atomic
    def create(self, request, *args, **kwargs):
        validated_docs = self._validate_additional_documents(request)
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            application = serializer.save()
        except IntegrityError:
            raise ValidationError({"detail": "Mobile number or email already exists."})

        self._persist_additional_documents(application, validated_docs, replace=False)
        application.refresh_from_db()

        return Response(
            self.get_serializer(application).data,
            status=status.HTTP_201_CREATED,
            headers=self.get_success_headers(serializer.data),
        )

    @transaction.atomic
    def update(self, request, *args, **kwargs):
        partial = kwargs.pop("partial", False)
        instance = self.get_object()
        validated_docs = self._validate_additional_documents(request)
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)

        try:
            application = serializer.save()
        except IntegrityError:
            raise ValidationError({"detail": "Mobile number or email already exists."})
        self._persist_additional_documents(application, validated_docs, replace=True)
        application.refresh_from_db()

        return Response(self.get_serializer(application).data)

    @staticmethod
    def _validate_additional_documents(request) -> dict[str, list]:
        errors = {}
        validated: dict[str, list] = {}

        for doc_type in DOCUMENT_TYPE_KEYS:
            files = request.FILES.getlist(f"{doc_type}_files")

            if not files:
                continue

            if len(files) > MAX_FILES_PER_TYPE:
                errors[f"{doc_type}_files"] = (
                    f"Maximum {MAX_FILES_PER_TYPE} files allowed per document type."
                )
                continue

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
        for doc_type, files in validated_docs.items():
            if replace:
                existing = StaffApplicationDocument.objects.filter(
                    application=application,
                    document_type=doc_type,
                )
                for doc in existing:
                    doc.file.delete(save=False)  
                existing.delete()

            for uploaded_file in files:
                StaffApplicationDocument.objects.create(
                    application=application,
                    document_type=doc_type,
                    file=uploaded_file,
                )

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