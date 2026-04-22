# Known Issues

## SSH key authentication in runner mode

- Some `ssh_key` credentials created through the original credentials form could be stored with broken formatting because the secret field used a single-line input instead of a multiline field.
- When that happened, the runner wrote malformed key material to a temporary file and OpenSSH failed with errors such as `Load key "/tmp/..." : error in libcrypto`.
- After public key authentication failed, the SSH client could fall back to password authentication, which made the target host log misleading `Failed password for root` entries even though the original intent was key-based authentication.
- The credentials screen has been updated to use a multiline textarea for `ssh_key` secrets, but any previously stored broken key needs to be recreated.
- `runner` SSH targets must use the format `ssh:<host>:<subject>` and the SSH username should come from the attached credential rather than being embedded in the target string.
