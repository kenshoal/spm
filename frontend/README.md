This is the ConnectSphere organiser frontend. Its current increment lets an organiser create, list and continue event-request drafts backed by the event request service.

## Getting Started

Start the event request service on port `8003`, then run the development server:

```bash
npm run dev
# or
yarn dev
# or
pnpm dev
# or
bun dev
```

Open [http://localhost:3000](http://localhost:3000) with your browser to see the result.

The local defaults use `http://127.0.0.1:8003` and organiser ID `test-organiser-heng-rui`. Override them when needed:

```bash
EVENT_REQUEST_API_URL=http://127.0.0.1:8003 \
EVENT_REQUEST_ORGANISER_ID=test-organiser-heng-rui \
npm run dev
```

`EVENT_REQUEST_ORGANISER_ID` is temporary development identity. Production authentication must replace the `X-Organiser-Id` header before deployment.

Run the frontend checks with:

```bash
npm test
npm run lint
npm run typecheck
npm run test:e2e
npm run build
```

The Playwright suite starts an isolated in-memory API on port `8103` and the
frontend on port `3100`. It exercises the browser workflow without changing the
shared Supabase project or requiring production authentication.

You can start editing the page by modifying `app/page.tsx`. The page auto-updates as you edit the file.

This project uses [`next/font`](https://nextjs.org/docs/app/building-your-application/optimizing/fonts) to automatically optimize and load [Geist](https://vercel.com/font), a new font family for Vercel.

## Learn More

To learn more about Next.js, take a look at the following resources:

- [Next.js Documentation](https://nextjs.org/docs) - learn about Next.js features and API.
- [Learn Next.js](https://nextjs.org/learn) - an interactive Next.js tutorial.

You can check out [the Next.js GitHub repository](https://github.com/vercel/next.js) - your feedback and contributions are welcome!

## Deploy on Vercel

The easiest way to deploy your Next.js app is to use the [Vercel Platform](https://vercel.com/new?utm_medium=default-template&filter=next.js&utm_source=create-next-app&utm_campaign=create-next-app-readme) from the creators of Next.js.

Check out our [Next.js deployment documentation](https://nextjs.org/docs/app/building-your-application/deploying) for more details.
