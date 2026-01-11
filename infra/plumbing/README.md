# foundation_network infra

This Terraform stack is intended to be applied **once per environment** to create shared networking primitives that multiple services can reuse.

It creates:
- VPC
- Public and private subnets
- Internet Gateway
- NAT Gateway (single)
- Route tables and associations

It outputs:
- `vpc_id`
- `public_subnet_ids`
- `private_subnet_ids`

## Usage

From this directory:

```bash
./scripts/manage.sh plan
./scripts/manage.sh apply
```

Destroy (rare; impacts anything using the VPC):

```bash
./scripts/manage.sh destroy
```
