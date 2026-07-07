{{- define "litellm-demo.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "litellm-demo.postgresName" -}}
{{- printf "%s-postgres" (include "litellm-demo.name" .) | trunc 63 | trimSuffix "-" -}}
{{- end -}}

