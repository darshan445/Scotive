FROM ruby:3.3.10-bookworm AS base

RUN apt-get update -qq && apt-get install -y --no-install-recommends \
    libpq-dev \
    postgresql-client \
  && rm -rf /var/lib/apt/lists/*

WORKDIR /app

ENV BUNDLE_PATH=/usr/local/bundle \
    RAILS_LOG_TO_STDOUT=true \
    PORT=3000

COPY Gemfile Gemfile.lock ./

# --- development: bind-mounts source; gems in a named volume ---
FROM base AS development
ENV RAILS_ENV=development
RUN bundle install
COPY . .
COPY bin/docker-entrypoint /usr/bin/docker-entrypoint
RUN chmod +x /usr/bin/docker-entrypoint
EXPOSE 3000
ENTRYPOINT ["docker-entrypoint"]
CMD ["bundle", "exec", "rails", "server", "-b", "0.0.0.0", "-p", "3000"]

# --- production: baked image, no source mount, no dev/test gems ---
FROM base AS production
ENV RAILS_ENV=production \
    BUNDLE_WITHOUT="development:test"
RUN bundle config set without "development test" \
  && bundle install --jobs 4 --retry 3
COPY . .
COPY bin/docker-entrypoint /usr/bin/docker-entrypoint
RUN chmod +x /usr/bin/docker-entrypoint
EXPOSE 3000
ENTRYPOINT ["docker-entrypoint"]
CMD ["bundle", "exec", "rails", "server", "-b", "0.0.0.0", "-p", "3000"]
