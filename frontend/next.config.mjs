/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  async redirects() {
    return [
      {
        source: "/overdue-invoice-reminder",
        destination: "/past-due-invoice-reminder",
        permanent: true,
      },
      {
        source: "/accounts-receivable-automation",
        destination: "/invoice-reminder-software",
        permanent: true,
      },
      {
        source: "/invoice-chasing-software",
        destination: "/invoice-reminder-software",
        permanent: true,
      },
      {
        source: "/chase-unpaid-invoices",
        destination: "/how-to-chase-outstanding-invoices",
        permanent: true,
      },
      {
        source: "/quickbooks-invoice-chasing",
        destination: "/quickbooks-invoice-reminders",
        permanent: true,
      },
      {
        source: "/freshbooks-invoice-chasing",
        destination: "/freshbooks-invoice-reminders",
        permanent: true,
      },
      {
        source: "/guides/invoice-follow-up-email-templates",
        destination: "/payment-reminder-email-template",
        permanent: true,
      },
      {
        source: "/guides/polite-reminder-for-unpaid-invoice",
        destination: "/past-due-invoice-reminder",
        permanent: true,
      },
      {
        source: "/guides/how-to-follow-up-on-an-invoice-politely",
        destination: "/how-to-chase-outstanding-invoices",
        permanent: true,
      },
      {
        source: "/guides/client-said-ill-pay-friday",
        destination: "/past-due-invoice-reminder",
        permanent: true,
      },
    ];
  },
  // Keep Vite-era env names working alongside NEXT_PUBLIC_*
  env: {
    REACT_APP_BACKEND_URL:
      process.env.NEXT_PUBLIC_BACKEND_URL || process.env.REACT_APP_BACKEND_URL || "",
  },
  images: {
    remotePatterns: [],
    // Local public/ icons used as <img> already; allow unoptimized brand assets
  },
};

export default nextConfig;
