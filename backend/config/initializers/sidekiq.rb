# frozen_string_literal: true

Sidekiq.configure_server do |config|
  config.redis = { url: ENV.fetch("REDIS_URL", "redis://localhost:6379/0") }
end

Sidekiq.configure_client do |config|
  config.redis = { url: ENV.fetch("REDIS_URL", "redis://localhost:6379/0") }
end

if Sidekiq.server?
  schedule = Rails.root.join("config/schedule.yml")
  if schedule.exist?
    hash = YAML.safe_load_file(schedule) || {}
    Sidekiq::Cron::Job.load_from_hash!(hash) if hash.is_a?(Hash) && hash.any?
  end
end
