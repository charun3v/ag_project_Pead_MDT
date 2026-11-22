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

    # Reference Lookups Management (Admin / SubAdmin)
    path('lookups/discussion-purposes/', views.manage_purposes_view, name='manage_purposes'),
    path('api/discussion-purposes/add/', views.api_add_discussion_purpose, name='api_add_discussion_purpose'),

    # Audit Logs
    path('audit-log/', views.audit_log_view, name='audit_log_view'),
]
