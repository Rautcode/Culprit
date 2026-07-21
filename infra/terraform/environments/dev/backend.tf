# Local state for the first apply — bootstrapping remote state needs a
# bucket that doesn't exist yet. After the first apply, create the state
# bucket (or reuse one), migrate with `terraform init -migrate-state`, and
# replace this with the S3 backend + DynamoDB lock table per docs/09.
# Local state on one operator's machine is acceptable exactly until a
# second operator exists.
