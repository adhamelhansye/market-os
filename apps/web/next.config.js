const createNextIntlPlugin = require("next-intl/plugin");

/** @type {import('next').NextConfig} */
const nextConfig = {
  transpilePackages: ["@marketing-os/shared-types"],
};

const withNextIntl = createNextIntlPlugin();

module.exports = withNextIntl(nextConfig);