# reverse-deepagent-external-delivery-provider-s3-compatible

S3-compatible `ExternalDeliveryProvider` plugin baseline for `reverse-deepagent`.

The package exposes the provider id `s3-compatible` through the
`reverse_deepagent.external_delivery_providers` Python entry-point group. Aliases
include `s3`, `s3-object`, and `minio`.

## Safety contract

- Registration and capability metadata are side-effect free: no environment
  reads, no client creation, no file reads, and no network access.
- Dry-run never performs network I/O and returns a reviewable upload plan.
- Apply mode requires both `package.mode == "apply"` and
  `approve_s3_delivery=True`.
- The provider uses stdlib `urllib.request` by default, or an injectable
  requester seam for tests/integrators. It does not depend on `boto3`.
- Result metadata records only redacted endpoint/upload URLs, digests, counts,
  booleans, and status codes. It never records raw query strings, userinfo,
  configured header values, request bodies, response bodies, or response headers.
- Inline URL userinfo/query material is blocked by default. Presigned URL mode
  may be enabled only with `allow_reviewed_presigned_url=True`, and even then the
  result stays fully redacted.

## Minimal config

For path-style S3-compatible endpoints:

```python
provider = create_s3_compatible_external_delivery_provider(
    endpoint_url="https://minio.example.test",
    bucket="reviewed-deliveries",
    object_name="tx-123/delivery-package.json",
    approve_s3_delivery=True,
)
```

For reviewed presigned PUT URLs:

```python
provider = create_s3_compatible_external_delivery_provider(
    upload_url="https://storage.example.test/bucket/object?X-Amz-Signature=...",
    allow_reviewed_presigned_url=True,
    approve_s3_delivery=True,
)
```

This baseline intentionally does not implement AWS SigV4 signing, bucket
management, multipart uploads, ACLs, or SDK-based clients.
