/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // Proxy /api/* to the backend at runtime so NEXT_PUBLIC_API_URL does not
  // need to be baked into the image at build time.
  // Set API_URL as a server-side environment variable (not NEXT_PUBLIC_).
  async rewrites() {
    const apiUrl = process.env.API_URL || 'http://api:8000';
    return [
      {
        source: '/api/:path*',
        destination: `${apiUrl}/:path*`,
      },
    ];
  },
};

module.exports = nextConfig;
