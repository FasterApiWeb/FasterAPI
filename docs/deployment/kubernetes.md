# Kubernetes

This guide deploys a FasterAPI application on Kubernetes with a Deployment,
Service, Ingress, HPA, and health probes.

## Prerequisites

- A running Kubernetes cluster (EKS, GKE, AKS, or local `kind`/`minikube`)
- `kubectl` configured
- Your Docker image in a registry the cluster can pull from

## Namespace

```bash
kubectl create namespace fasterapi
```

## ConfigMap and Secret

```yaml
# k8s/configmap.yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: fasterapi-config
  namespace: fasterapi
data:
  ENV: "production"
  WORKERS: "4"
```

```yaml
# k8s/secret.yaml
apiVersion: v1
kind: Secret
metadata:
  name: fasterapi-secrets
  namespace: fasterapi
type: Opaque
stringData:
  DATABASE_URL: "postgresql+asyncpg://user:pass@postgres-svc/mydb"
  SECRET_KEY: "your-production-secret-key"
```

```bash
kubectl apply -f k8s/configmap.yaml
kubectl apply -f k8s/secret.yaml
```

## Deployment

```yaml
# k8s/deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: fasterapi
  namespace: fasterapi
spec:
  replicas: 3
  selector:
    matchLabels:
      app: fasterapi
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxUnavailable: 1
      maxSurge: 1
  template:
    metadata:
      labels:
        app: fasterapi
    spec:
      containers:
        - name: api
          image: myregistry/my-fasterapi:latest
          imagePullPolicy: Always
          ports:
            - containerPort: 8000
          envFrom:
            - configMapRef:
                name: fasterapi-config
            - secretRef:
                name: fasterapi-secrets
          resources:
            requests:
              cpu: "250m"
              memory: "256Mi"
            limits:
              cpu: "1000m"
              memory: "512Mi"
          livenessProbe:
            httpGet:
              path: /health
              port: 8000
            initialDelaySeconds: 10
            periodSeconds: 15
            failureThreshold: 3
          readinessProbe:
            httpGet:
              path: /health
              port: 8000
            initialDelaySeconds: 5
            periodSeconds: 10
            failureThreshold: 3
          startupProbe:
            httpGet:
              path: /health
              port: 8000
            failureThreshold: 30
            periodSeconds: 3
```

## Service

```yaml
# k8s/service.yaml
apiVersion: v1
kind: Service
metadata:
  name: fasterapi-svc
  namespace: fasterapi
spec:
  selector:
    app: fasterapi
  ports:
    - port: 80
      targetPort: 8000
  type: ClusterIP
```

## Ingress (Nginx Ingress Controller)

```yaml
# k8s/ingress.yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: fasterapi-ingress
  namespace: fasterapi
  annotations:
    nginx.ingress.kubernetes.io/ssl-redirect: "true"
    cert-manager.io/cluster-issuer: "letsencrypt-prod"
spec:
  tls:
    - hosts:
        - api.example.com
      secretName: fasterapi-tls
  rules:
    - host: api.example.com
      http:
        paths:
          - path: /
            pathType: Prefix
            backend:
              service:
                name: fasterapi-svc
                port:
                  number: 80
```

## Horizontal Pod Autoscaler

Scale based on CPU utilisation:

```yaml
# k8s/hpa.yaml
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: fasterapi-hpa
  namespace: fasterapi
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: fasterapi
  minReplicas: 2
  maxReplicas: 20
  metrics:
    - type: Resource
      resource:
        name: cpu
        target:
          type: Utilization
          averageUtilization: 70
    - type: Resource
      resource:
        name: memory
        target:
          type: Utilization
          averageUtilization: 80
```

## Apply all manifests

```bash
kubectl apply -f k8s/
kubectl rollout status deployment/fasterapi -n fasterapi
```

## Rolling update

```bash
# Update image tag
kubectl set image deployment/fasterapi api=myregistry/my-fasterapi:v2 -n fasterapi
kubectl rollout status deployment/fasterapi -n fasterapi

# Rollback if needed
kubectl rollout undo deployment/fasterapi -n fasterapi
```

## Useful commands

```bash
# Logs
kubectl logs -l app=fasterapi -n fasterapi --tail=100 -f

# Shell into pod
kubectl exec -it deploy/fasterapi -n fasterapi -- /bin/bash

# Scale manually
kubectl scale deployment fasterapi --replicas=5 -n fasterapi
```

## Helm chart

For reusable parameterised deployments, package the manifests as a Helm chart:

```bash
helm create fasterapi-chart
# Edit templates/ with the manifests above
helm upgrade --install fasterapi ./fasterapi-chart \
  --namespace fasterapi \
  --set image.tag=v2 \
  --set replicas=3
```

## Next steps

- [Docker](docker.md) — build the image deployed here.
- [Cloud Services](cloud.md) — managed Kubernetes on AWS/GCP/Azure.
