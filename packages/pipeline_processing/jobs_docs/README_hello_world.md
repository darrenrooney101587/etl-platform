# Hello World Job

Hello-world smoke-test job for the file_processing package.

This job exists to support Kubernetes and CI smoke checks. It intentionally
avoids external dependencies (S3, DB, AWS) and simply logs a message.

## Usage

```bash
./packages/file_processing/scripts/commands.sh hello_world --message "Greetings from container"
```
