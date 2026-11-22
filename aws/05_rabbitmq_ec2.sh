#!/usr/bin/env bash
# Lanza una EC2 t3.large con RabbitMQ (rabbitmq:3-management) en Docker. Ejecutar en CloudShell.
# Variables obligatorias: MI_IP (tu IP publica, IPv4) y RABBIT_PASS.
# Opcional: KEY_NAME (key pair para SSH), RABBIT_USER (por defecto ep3).
# Nota: el user-data queda visible en la consola EC2; usar una password de laboratorio.
set -euo pipefail

REGION=us-east-1
NOMBRE=ep3-rabbitmq
SG_NOMBRE=ep3-rabbitmq-sg
MI_IP=${MI_IP:?definir MI_IP=<tu IP publica IPv4>}
RABBIT_USER=${RABBIT_USER:-ep3}
RABBIT_PASS=${RABBIT_PASS:?definir RABBIT_PASS=<password de RabbitMQ>}
KEY_NAME=${KEY_NAME:-}

AMI=$(aws ssm get-parameter --name /aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-x86_64 \
  --query 'Parameter.Value' --output text --region "$REGION")

VPC=$(aws ec2 describe-vpcs --filters Name=isDefault,Values=true \
  --query 'Vpcs[0].VpcId' --output text --region "$REGION")

SG_ID=$(aws ec2 describe-security-groups \
  --filters "Name=group-name,Values=$SG_NOMBRE" "Name=vpc-id,Values=$VPC" \
  --query 'SecurityGroups[0].GroupId' --output text --region "$REGION")
if [[ -z "$SG_ID" || "$SG_ID" == "None" ]]; then
  SG_ID=$(aws ec2 create-security-group --group-name "$SG_NOMBRE" \
    --description "RabbitMQ EP3 - acceso solo desde mi IP" --vpc-id "$VPC" \
    --query 'GroupId' --output text --region "$REGION")
fi
echo "Security group: $SG_ID"

# Duplicados esperados si la regla ya existe
for puerto in 22 5672 15672; do
  aws ec2 authorize-security-group-ingress --group-id "$SG_ID" --protocol tcp \
    --port "$puerto" --cidr "$MI_IP/32" --region "$REGION" >/dev/null 2>&1 \
    || echo "Regla puerto $puerto ya existia (ok)"
done

UD=$(mktemp)
trap 'rm -f "$UD"' EXIT
cat > "$UD" <<EOF
#!/bin/bash
set -euo pipefail
dnf install -y docker
systemctl enable --now docker
docker run -d --name rabbitmq --restart unless-stopped \
  -p 5672:5672 -p 15672:15672 \
  -e RABBITMQ_DEFAULT_USER=$RABBIT_USER -e RABBITMQ_DEFAULT_PASS=$RABBIT_PASS \
  rabbitmq:3-management
EOF

ARGS=(--image-id "$AMI" --instance-type t3.large --count 1
  --iam-instance-profile Name=LabInstanceProfile
  --security-group-ids "$SG_ID"
  --user-data "file://$UD"
  --tag-specifications "ResourceType=instance,Tags=[{Key=Name,Value=$NOMBRE}]"
  --region "$REGION")
if [[ -n "$KEY_NAME" ]]; then
  ARGS+=(--key-name "$KEY_NAME")
fi

ID=$(aws ec2 run-instances "${ARGS[@]}" --query 'Instances[0].InstanceId' --output text)
aws ec2 wait instance-running --instance-ids "$ID" --region "$REGION"
IP=$(aws ec2 describe-instances --instance-ids "$ID" --region "$REGION" \
  --query 'Reservations[0].Instances[0].PublicIpAddress' --output text)

echo "INSTANCE_ID=$ID"
echo "IP_PUBLICA=$IP"
echo "Consola de gestion RabbitMQ: http://$IP:15672 (esperar 3-5 min a que Docker descargue la imagen)"
echo "AMQP: amqp://$RABBIT_USER:<password>@$IP:5672"
