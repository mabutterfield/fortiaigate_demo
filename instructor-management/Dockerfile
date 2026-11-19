FROM python:3.12-slim
WORKDIR /app
COPY instructor-management /app/instructor-management
COPY chatbot/scenarios/examples /app/chatbot/scenarios/examples
COPY experiments/faig-api-lab/scenario-catalog.json /app/experiments/faig-api-lab/scenario-catalog.json
ENV LAB_REPO_ROOT=/app PYTHONDONTWRITEBYTECODE=1
USER 10001:10001
EXPOSE 8080
CMD ["python", "/app/instructor-management/service.py"]
