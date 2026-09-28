# MBstudio dark design preview

This temporary branch contains a public page and an isolated cabinet concept for MBstudio. The cabinet uses illustrative local state. It does not authenticate, read customer data, submit requests, or save changes to the production service.

To rebuild the static bundle:

```sh
cd preview/mbstudio-src
npm ci
npm run build
cp -a dist/client/. ../../public/design-preview/mbstudio-noir/
```

The branch's `Dockerfile.vercel` serves only the resulting static files at `/` and `/cabinet/`. The existing `main` branch retains the SCENA application and its production deployment.
