/** @type {import('next').NextConfig} */
const nextConfig = {
  // Keep the backend URL server-side-configurable via env var rather than
  // hardcoded, so the same build works against local/staging/prod backends.
};

module.exports = nextConfig;
