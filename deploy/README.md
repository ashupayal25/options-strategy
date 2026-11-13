# Deploying to AWS

What gets created: one small EC2 instance (Amazon Linux 2023, ARM) with an **Elastic IP**, a **private S3 bucket** for state
(positions, reports, cached bars), an instance role that can only use that bucket's `otm/` prefix and read SSM parameters under your
prefix, and a security group with **no inbound ports** (you connect through SSM Session Manager, not SSH). Two systemd timers run the app
at 09:40 and 15:20 IST, Monday to Friday. The app sends Telegram messages and places no orders.

Rough cost: a t4g.micro instance plus the Elastic IP is a few dollars a month; S3 is pennies.

## 0. Prerequisites

- AWS CLI configured (`aws sts get-caller-identity` works) and permission to create IAM roles, EC2, S3, SSM parameters.
- The repo pushed to a git remote (GitHub or similar). If it is **private**, create a read-only access token and store it in SSM (step 2).
- A VPC and a **public** subnet (route to an internet gateway). The default VPC works:
  ```bash
  aws ec2 describe-vpcs --filters Name=isDefault,Values=true --query "Vpcs[0].VpcId" --output text
  aws ec2 describe-subnets --filters Name=vpc-id,Values=<vpc-id> --query "Subnets[].[SubnetId,AvailabilityZone,MapPublicIpOnLaunch]" --output table
  ```

## 1. Create the Telegram bot

1. In Telegram, talk to **@BotFather**, send `/newbot`, and copy the bot token it gives you.
2. Open a chat with your new bot and send it any message.
3. Get your chat id: `https://api.telegram.org/bot<TOKEN>/getUpdates` shows `"chat":{"id": ...}`.
4. Treat the token like a password: do not paste it into chats, tickets or the repo.

## 2. Store the secrets in SSM Parameter Store

Run these yourself (they prompt for nothing, so type the values locally):

```bash
aws ssm put-parameter --name /otm-strategy/telegram/bot_token --type SecureString --value "<BOT_TOKEN>"
aws ssm put-parameter --name /otm-strategy/telegram/chat_id   --type SecureString --value "<CHAT_ID>"
# only for a private repo:
aws ssm put-parameter --name /otm-strategy/git/token --type SecureString --value "<READ_ONLY_GIT_TOKEN>"
```

## 3. Deploy the stack

```bash
aws cloudformation deploy \
  --template-file deploy/cloudformation.yaml \
  --stack-name otm-signal \
  --capabilities CAPABILITY_IAM \
  --parameter-overrides VpcId=<vpc-id> SubnetId=<public-subnet-id> \
      RepoUrl=https://github.com/<you>/<repo>.git RepoRef=main \
      GitTokenParameter=/otm-strategy/git/token      # omit this line for a public repo
aws cloudformation describe-stacks --stack-name otm-signal --query "Stacks[0].Outputs" --output table
```

The outputs show the instance id, the Elastic IP and the bucket name. The first boot takes a few minutes (it installs Python, clones the
repo, builds the virtualenv and enables the timers).

## 4. Verify

```bash
aws ssm start-session --target <instance-id>          # needs the Session Manager plugin installed locally
# on the instance:
systemctl list-timers 'otm-*'
sudo -u otm bash -c 'set -a; . /etc/otm/otm.env; set +a; /opt/otm/venv/bin/otm notify-test'   # a Telegram message should arrive
sudo -u otm bash -c 'set -a; . /etc/otm/otm.env; set +a; /opt/otm/venv/bin/otm report'        # prints today's report and saves it to S3
```

Record the positions you actually trade the same way (`otm record ...`, `otm close --id N`), because the app only knows what you tell it.

## 5. Day to day

| What | Command (on the instance) |
|---|---|
| See the last runs | `journalctl -u otm-entry.service -u otm-exit.service --since "2 days ago"` |
| Run one now | `sudo systemctl start otm-exit.service` |
| Next scheduled runs | `systemctl list-timers 'otm-*'` |
| Update the code | `sudo bash /opt/otm/app/deploy/update.sh` |
| Settings | edit `/etc/otm/otm.env` (for example `OTM_LOTS=3`), then nothing else: the next run picks it up |

The timers use `Asia/Kolkata` directly, so the instance clock zone does not matter. On days the exchange is closed (holidays) the 3:20 PM run
sends nothing; on an entry-day morning with no bar yet, the ticket carries a "confirm the market is open" warning.

## 6. Things to know

- **Yahoo from AWS:** Yahoo can throttle or block cloud IP ranges. The app retries, falls back to the last cached bars (kept in S3) with a
  data warning in the report, and sends a Telegram error alert if it cannot produce a report. If this happens often, we switch the data source.
- **The Elastic IP** is for later: if you add broker automation, Zerodha's API may need a static IP, and this is it.
- **Private repo token:** it is stored only in SSM and passed to git for the single command, never written to disk.
- **Teardown:** `aws cloudformation delete-stack --stack-name otm-signal`. The S3 bucket is retained on purpose (it holds your positions
  history); delete it separately if you want it gone.
