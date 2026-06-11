#!/usr/bin/env bash
# One-time AWS infra for Garmin CI token self-healing (Secrets Manager + GitHub OIDC).
# Requires: AWS CLI v2, credentials with IAM + Secrets Manager create permissions.
# Env: AWS_REGION (default us-east-1), GITHUB_REPO (default deep0410/garmin-ai-notifier).
# Prints ROLE_ARN — set as GitHub secret AWS_ROLE_ARN.
set -euo pipefail

AWS_REGION="${AWS_REGION:-us-east-1}"
GITHUB_REPO="${GITHUB_REPO:-deep0410/garmin-ai-notifier}"
SECRET_NAME="${SECRET_NAME:-garmin-ai-notifier/garmin-tokens}"
ROLE_NAME="${ROLE_NAME:-garmin-ai-notifier-github-actions}"
POLICY_NAME="${POLICY_NAME:-garmin-ai-notifier-secrets-access}"

AWS_ACCOUNT_ID="$(aws sts get-caller-identity --query Account --output text)"
echo "AWS account: $AWS_ACCOUNT_ID  region: $AWS_REGION  repo: $GITHUB_REPO"

OIDC_ARN="arn:aws:iam::${AWS_ACCOUNT_ID}:oidc-provider/token.actions.githubusercontent.com"
EXISTING_OIDC="$(aws iam list-open-id-connect-providers \
  --query "OpenIDConnectProviderList[?Arn=='${OIDC_ARN}'].Arn" \
  --output text 2>/dev/null || true)"

if [[ -z "$EXISTING_OIDC" ]]; then
  echo "Creating GitHub OIDC provider..."
  aws iam create-open-id-connect-provider \
    --url https://token.actions.githubusercontent.com \
    --client-id-list sts.amazonaws.com \
    --thumbprint-list 6938fd4d98bab03faadb97b34396831e3780aea1
else
  echo "GitHub OIDC provider already exists."
fi

if aws secretsmanager describe-secret --secret-id "$SECRET_NAME" --region "$AWS_REGION" >/dev/null 2>&1; then
  echo "Secrets Manager secret already exists: $SECRET_NAME"
else
  echo "Creating Secrets Manager secret: $SECRET_NAME"
  aws secretsmanager create-secret \
    --name "$SECRET_NAME" \
    --description "Garmin Connect DI tokens (base64 tar of ~/.garminconnect)" \
    --secret-string "UNINITIALIZED" \
    --region "$AWS_REGION"
fi

SECRET_ARN="$(aws secretsmanager describe-secret \
  --secret-id "$SECRET_NAME" \
  --region "$AWS_REGION" \
  --query ARN --output text)"
echo "SECRET_ARN=$SECRET_ARN"

POLICY_ARN="arn:aws:iam::${AWS_ACCOUNT_ID}:policy/${POLICY_NAME}"
POLICY_DOC="$(mktemp)"
trap 'rm -f "$POLICY_DOC"' EXIT

cat > "$POLICY_DOC" <<EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "GarminTokenSecretReadWrite",
      "Effect": "Allow",
      "Action": [
        "secretsmanager:GetSecretValue",
        "secretsmanager:PutSecretValue",
        "secretsmanager:DescribeSecret"
      ],
      "Resource": "${SECRET_ARN}"
    }
  ]
}
EOF

if aws iam get-policy --policy-arn "$POLICY_ARN" >/dev/null 2>&1; then
  echo "IAM policy already exists: $POLICY_NAME"
else
  echo "Creating IAM policy: $POLICY_NAME"
  aws iam create-policy \
    --policy-name "$POLICY_NAME" \
    --policy-document "file://${POLICY_DOC}"
fi

TRUST_DOC="$(mktemp)"
trap 'rm -f "$POLICY_DOC" "$TRUST_DOC"' EXIT

cat > "$TRUST_DOC" <<EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Federated": "arn:aws:iam::${AWS_ACCOUNT_ID}:oidc-provider/token.actions.githubusercontent.com"
      },
      "Action": "sts:AssumeRoleWithWebIdentity",
      "Condition": {
        "StringEquals": {
          "token.actions.githubusercontent.com:aud": "sts.amazonaws.com"
        },
        "StringLike": {
          "token.actions.githubusercontent.com:sub": "repo:${GITHUB_REPO}:*"
        }
      }
    }
  ]
}
EOF

if aws iam get-role --role-name "$ROLE_NAME" >/dev/null 2>&1; then
  echo "IAM role already exists: $ROLE_NAME"
else
  echo "Creating IAM role: $ROLE_NAME"
  aws iam create-role \
    --role-name "$ROLE_NAME" \
    --assume-role-policy-document "file://${TRUST_DOC}"
fi

aws iam attach-role-policy \
  --role-name "$ROLE_NAME" \
  --policy-arn "$POLICY_ARN" 2>/dev/null || true

ROLE_ARN="arn:aws:iam::${AWS_ACCOUNT_ID}:role/${ROLE_NAME}"

echo ""
echo "=== Bootstrap complete ==="
echo "ROLE_ARN=$ROLE_ARN"
echo "GARMIN_TOKEN_SECRET_NAME=$SECRET_NAME"
echo ""
echo "Next steps:"
echo "  1. gh secret set AWS_ROLE_ARN --body \"$ROLE_ARN\""
echo "  2. python scripts/mint_token.py"
echo "  3. bash scripts/seed_aws_secret.sh"
echo ""
aws iam get-role --role-name "$ROLE_NAME" --query 'Role.Arn' --output text
aws secretsmanager describe-secret --secret-id "$SECRET_NAME" --region "$AWS_REGION" --query '[Name,ARN]' --output text
