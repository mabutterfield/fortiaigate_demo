{{- define "lab-chatbot.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" -}}
{{- end -}}
{{- define "lab-chatbot.labels" -}}
app.kubernetes.io/name: {{ include "lab-chatbot.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end -}}
