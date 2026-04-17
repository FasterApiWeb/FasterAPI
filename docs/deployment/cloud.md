# Cloud Deployment

## AWS

### AWS App Runner (simplest)

App Runner builds from a container image or source code and handles scaling
automatically.

1. Push your Docker image to ECR:

```bash
aws ecr create-repository --repository-name my-fasterapi
aws ecr get-login-password | docker login --username AWS --password-stdin \
  <account-id>.dkr.ecr.<region>.amazonaws.com
docker tag my-fasterapi-app:latest \
  <account-id>.dkr.ecr.<region>.amazonaws.com/my-fasterapi:latest
docker push <account-id>.dkr.ecr.<region>.amazonaws.com/my-fasterapi:latest
```

2. Create an App Runner service:

```bash
aws apprunner create-service \
  --service-name my-fasterapi \
  --source-configuration '{
    "ImageRepository": {
      "ImageIdentifier": "<account-id>.dkr.ecr.<region>.amazonaws.com/my-fasterapi:latest",
      "ImageRepositoryType": "ECR"
    }
  }' \
  --instance-configuration '{"Cpu": "1 vCPU", "Memory": "2 GB"}'
```

### AWS ECS (Fargate)

ECS Fargate runs containers without managing servers.

`task-definition.json`:

```json
{
  "family": "fasterapi",
  "networkMode": "awsvpc",
  "requiresCompatibilities": ["FARGATE"],
  "cpu": "512",
  "memory": "1024",
  "containerDefinitions": [
    {
      "name": "api",
      "image": "<account-id>.dkr.ecr.<region>.amazonaws.com/my-fasterapi:latest",
      "portMappings": [{"containerPort": 8000}],
      "environment": [
        {"name": "ENV", "value": "production"}
      ],
      "secrets": [
        {"name": "DATABASE_URL", "valueFrom": "arn:aws:secretsmanager:...:secret:db-url"},
        {"name": "SECRET_KEY",   "valueFrom": "arn:aws:secretsmanager:...:secret:sk"}
      ],
      "healthCheck": {
        "command": ["CMD-SHELL", "curl -f http://localhost:8000/health || exit 1"],
        "interval": 30,
        "timeout": 5,
        "retries": 3
      },
      "logConfiguration": {
        "logDriver": "awslogs",
        "options": {
          "awslogs-group": "/ecs/fasterapi",
          "awslogs-region": "us-east-1",
          "awslogs-stream-prefix": "ecs"
        }
      }
    }
  ]
}
```

### AWS Lambda (serverless)

Use **Mangum** to wrap the FasterAPI ASGI app for Lambda + API Gateway:

```bash
pip install mangum
```

```python
# handler.py
from mangum import Mangum
from main import app

handler = Mangum(app, lifespan="off")
```

Deploy with the Serverless Framework or AWS SAM.

---

## Google Cloud Platform

### Cloud Run

Cloud Run is the simplest managed container service on GCP.

```bash
# Build and push to Artifact Registry
gcloud builds submit --tag gcr.io/PROJECT_ID/my-fasterapi

# Deploy
gcloud run deploy my-fasterapi \
  --image gcr.io/PROJECT_ID/my-fasterapi \
  --platform managed \
  --region us-central1 \
  --allow-unauthenticated \
  --port 8000 \
  --memory 512Mi \
  --concurrency 80 \
  --set-env-vars ENV=production \
  --set-secrets DATABASE_URL=db-url:latest,SECRET_KEY=sk:latest
```

### Cloud Run with custom domain + TLS

```bash
gcloud run domain-mappings create \
  --service my-fasterapi \
  --domain api.example.com \
  --region us-central1
```

---

## Microsoft Azure

### Azure Container Apps

```bash
# Create resource group and environment
az group create --name my-rg --location eastus
az containerapp env create --name my-env --resource-group my-rg --location eastus

# Deploy
az containerapp create \
  --name my-fasterapi \
  --resource-group my-rg \
  --environment my-env \
  --image myregistry.azurecr.io/my-fasterapi:latest \
  --target-port 8000 \
  --ingress external \
  --min-replicas 1 \
  --max-replicas 10 \
  --env-vars ENV=production \
  --secrets db-url=secretref:DATABASE_URL sk=secretref:SECRET_KEY
```

### Azure App Service

```bash
az webapp create \
  --resource-group my-rg \
  --plan my-plan \
  --name my-fasterapi \
  --deployment-container-image-name myregistry.azurecr.io/my-fasterapi:latest

az webapp config appsettings set \
  --resource-group my-rg \
  --name my-fasterapi \
  --settings DATABASE_URL="@Microsoft.KeyVault(SecretUri=...)" ENV=production
```

---

## Secrets management

| Platform | Service |
|---|---|
| AWS | Secrets Manager / Parameter Store |
| GCP | Secret Manager |
| Azure | Key Vault |
| Any | HashiCorp Vault |

Never bake secrets into container images or commit `.env` files.

## Auto-scaling considerations

- FasterAPI with uvicorn scales **horizontally** — add more replicas behind a load
  balancer.
- For CPU-bound work, use Python 3.13's `SubInterpreterPool` to parallelise within a
  single process before adding replicas.
- Session/state management (JWT is stateless; DB connections need a pool per replica).

## Next steps

- [Docker](docker.md) — containerise before deploying to cloud.
- [Kubernetes](kubernetes.md) — advanced orchestration.
