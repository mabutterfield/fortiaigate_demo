{{- define "lab-management.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" -}}
{{- end -}}
{{- define "lab-management.labels" -}}
app.kubernetes.io/name: {{ include "lab-management.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end -}}
