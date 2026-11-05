# vendor/ - internal packages, installed without touching public PyPI

The shared identity library (`i2-platform-auth`, imported as `platform_auth`) is NOT on public PyPI, and an unrelated
package called `platform-auth` is. So it is never listed in requirements and never resolved from an index that
includes PyPI (that would be a dependency-confusion risk). The image installs it from here, offline:

    make vendor PLATFORM_AUTH=<i2-platform-auth folder>      # builds the wheel into vendor/

Commit the wheel (it is your own code, a few KB) so the pipeline and image builds need nothing else.
Once an internal package feed exists, the pipeline can download the wheel from it into vendor/ instead.
Laptop: `pip install -e <i2-platform-auth folder>` (a path, never a bare name).
`<i2-platform-auth folder>` is your clone of the i2-platform-auth repo (in the prototype: platform/platform_auth).
