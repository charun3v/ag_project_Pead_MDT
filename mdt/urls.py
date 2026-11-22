from django.urls import path
from . import views

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    
    # Patient URLs
    path('patients/search/', views.patient_search, name='patient_search'),
    path('patients/new/', views.patient_create, name='patient_create'),
    path('patients/<str:mr_no>/edit/', views.patient_edit, name='patient_edit'),
    path('patients/<str:mr_no>/delete/', views.patient_delete_view, name='patient_delete'),
    path('api/districts/', views.api_districts, name='api_districts'),
    
    # Clinical Presentation URLs
    path('clinical/new/<str:mr_no>/', views.clinical_create, name='clinical_create'),
    path('clinical/<int:clinical_id>/', views.clinical_edit, name='clinical_edit'),
    path('clinical/<int:clinical_id>/delete/', views.clinical_delete_view, name='clinical_delete'),
    path('clinical/<int:clinical_id>/inv/add/<str:inv_type>/', views.investigation_add, name='investigation_add'),
    path('investigation/delete/<str:inv_type>/<int:inv_id>/', views.investigation_delete, name='investigation_delete'),
    
    # MDT Consensus URLs
    path('consensus/<int:consensus_id>/', views.consensus_edit, name='consensus_edit'),
    path('consensus/<int:consensus_id>/live/', views.live_presentation, name='live_presentation'),
    
    # Reports
    path('reports/clinical/<int:clinical_id>/', views.report_clinical_summary, name='report_clinical_summary'),
    path('reports/mdt/<int:consensus_id>/', views.report_mdt_full, name='report_mdt_full'),
    
    # User Account Management (Admin / SubAdmin)
    path('users/', views.user_list_view, name='user_list'),
    path('users/new/', views.user_create_view, name='user_create'),
    path('users/<int:user_id>/edit/', views.user_edit_view, name='user_edit'),
    path('users/<int:user_id>/toggle-active/', views.user_toggle_active_view, name='user_toggle_active'),
    path('users/<int:user_id>/delete/', views.user_delete_view, name='user_delete'),
    
    # Data Export (Admin / SubAdmin)
    path('export/', views.export_hub_view, name='export_hub'),
    path('export/patients/', views.export_patients_csv_view, name='export_patients_csv'),
    path('export/mdt/', views.export_mdt_csv_view, name='export_mdt_csv'),
    path('export/investigations/', views.export_investigations_csv_view, name='export_investigations_csv'),
    path('export/audit-logs/', views.export_audit_logs_csv_view, name='export_audit_logs_csv'),
    path('export/all-zip/', views.export_all_zip_view, name='export_all_zip'),

    # Reference Lookups Management (Scheduler Database Design)
    path('lookups/', views.lookup_manager_view, name='lookup_manager'),
    path('lookups/discussion-purposes/', views.manage_purposes_view, name='manage_purposes'),
    path('lookups/<str:category>/', views.lookup_manager_view, name='lookup_manager_category'),
    path('lookups/<str:category>/add/', views.lookup_add_view, name='lookup_add'),
    path('lookups/<str:category>/<int:item_id>/toggle/', views.lookup_toggle_view, name='lookup_toggle'),
    path('lookups/<str:category>/<int:item_id>/delete/', views.lookup_delete_view, name='lookup_delete'),
    path('lookups/<str:category>/reorder/', views.lookup_reorder_view, name='lookup_reorder'),
    path('api/discussion-purposes/add/', views.api_add_discussion_purpose, name='api_add_discussion_purpose'),
    path('api/discussion-purposes/reorder/', views.api_reorder_discussion_purposes, name='api_reorder_discussion_purposes'),

    # Dedicated Gynae-Style Multi-Modality Investigation Pages
    path('clinical/<int:clinical_id>/investigations/', views.investigations_hub_view, name='investigations_hub'),
    path('clinical/<int:clinical_id>/investigations/blood/add/', views.blood_form_view, name='blood_add'),
    path('clinical/<int:clinical_id>/investigations/blood/<int:inv_id>/edit/', views.blood_form_view, name='blood_edit'),
    path('clinical/<int:clinical_id>/investigations/imaging/add/', views.imaging_form_view, name='imaging_add'),
    path('clinical/<int:clinical_id>/investigations/imaging/<int:inv_id>/edit/', views.imaging_form_view, name='imaging_edit'),
    path('clinical/<int:clinical_id>/investigations/pathology/add/', views.pathology_form_view, name='pathology_add'),
    path('clinical/<int:clinical_id>/investigations/pathology/<int:inv_id>/edit/', views.pathology_form_view, name='pathology_edit'),
    path('clinical/<int:clinical_id>/investigations/molecular/add/', views.molecular_form_view, name='molecular_add'),
    path('clinical/<int:clinical_id>/investigations/molecular/<int:inv_id>/edit/', views.molecular_form_view, name='molecular_edit'),

    # Audit Logs
    path('audit-log/', views.audit_log_view, name='audit_log_view'),
]
