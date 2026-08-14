import createMiddleware from "next-intl/middleware";

import { routing } from "@/i18n/routing";

export default createMiddleware(routing);

export const config = {
  // Skip internal Next.js paths and API routes.
  matcher: ["/", "/(en|ar)/:path*"],
};