### Changed

- The built viewer frontend (`_view/www/dist`) ships in the package, so `inspect-dataset view` works from an install without building the frontend or installing Node.

### Fixed

- Opening or reloading a viewer URL other than the root no longer returns 404. The server falls back to `index.html` for client-side routes, so deep links work.
