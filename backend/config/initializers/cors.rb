# frozen_string_literal: true

# FRONTEND_URL is the canonical site (used for OAuth redirects). CORS also allows
# the www / apex twin so https://www.scotive.com can call api.scotive.com.
frontend_origins = ENV.fetch("FRONTEND_URL", "http://localhost:3001").split(",").flat_map do |raw|
  url = raw.strip.chomp("/")
  next [] if url.empty?

  uri = URI.parse(url)
  host = uri.host
  next [url] if host.blank? || host == "localhost" || host.match?(/\A\d{1,3}(?:\.\d{1,3}){3}\z/)

  hosts = host.start_with?("www.") ? [host, host.delete_prefix("www.")] : [host, "www.#{host}"]
  port = uri.port != uri.default_port ? ":#{uri.port}" : ""
  hosts.uniq.map { |h| "#{uri.scheme}://#{h}#{port}" }
end.uniq

Rails.application.config.middleware.insert_before 0, Rack::Cors do
  allow do
    origins(*frontend_origins)

    resource "*",
      headers: :any,
      methods: %i[get post put patch delete options head],
      expose: [ "Authorization" ],
      credentials: true
  end
end
