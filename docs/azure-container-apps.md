# Azure Container Apps Deployment Notes

Foundry Local is designed for local model execution. For a student-credit friendly
Azure story, deploy the web app and API as a demo surface, while keeping the AI runtime
local-first when presenting from your machine.

## Cost-Safe Plan

Use the $100 student credit for:

- Azure Container Registry
- Azure Container Apps
- Optional Log Analytics workspace

Avoid GPU inference in Azure for this project unless explicitly required. The core
learning objective is Foundry Local.

## Build Locally

```bash
docker build -t summer-school-rag-agent:latest .
docker compose up --build
```

## Azure CLI Sketch

Replace names with your own values.

```bash
az login
az group create --name rg-summer-rag --location westeurope

az acr create \
  --resource-group rg-summer-rag \
  --name summerschoolragacr \
  --sku Basic \
  --admin-enabled true

az acr login --name summerschoolragacr
docker tag summer-school-rag-agent:latest summerschoolragacr.azurecr.io/summer-school-rag-agent:latest
docker push summerschoolragacr.azurecr.io/summer-school-rag-agent:latest

az containerapp env create \
  --name env-summer-rag \
  --resource-group rg-summer-rag \
  --location westeurope

az containerapp create \
  --name app-summer-rag-api \
  --resource-group rg-summer-rag \
  --environment env-summer-rag \
  --image summerschoolragacr.azurecr.io/summer-school-rag-agent:latest \
  --target-port 8000 \
  --ingress external \
  --min-replicas 0 \
  --max-replicas 1
```

## Presentation Recommendation

For the final presentation, use the local app first. Mention Azure Container Apps as
the optional deployment path and explain why inference remains local:

- lower cost
- offline-capable demos
- private documents stay on the user's machine
- aligns with Foundry Local's purpose
