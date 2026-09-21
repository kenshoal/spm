This is the ConnectSphere organiser frontend. An authenticated organiser can
save incomplete drafts, submit a complete new request or saved draft, and track
requests using All, Draft, Submitted and Completed tabs. Submitted requests
are read-only.

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

The sign-up and login page is at [http://localhost:3000/auth](http://localhost:3000/auth).
Start authService on port `8001` (for example, `docker compose up auth-service`) or set
`AUTH_SERVICE_URL` for the Next.js server. If running authService directly with Uvicorn on
port `8000`, set `AUTH_SERVICE_URL=http://127.0.0.1:8000`. A successful login sets an
HTTP-only, same-site browser cookie for the access token and opens the protected
event-request area. Log out removes the local cookie; the session expires with
the access token (currently no automatic refresh).

The event-request API defaults to `http://127.0.0.1:8003`. Override it when needed:

```bash
EVENT_REQUEST_API_URL=http://127.0.0.1:8003 \
npm run dev
```

The Next.js server forwards the session token to eventRequestService. Never put
the Supabase secret key in frontend environment variables.

Run the frontend checks with:

```bash
npm test
npm run lint
npm run typecheck
npm run test:e2e
npm run build
```

The Playwright suite starts isolated auth and event-request APIs on ports `8104`
and `8103`, plus a frontend on `3100`. It exercises the browser workflow without
changing the shared Supabase project.

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
