# frozen_string_literal: true

require "faraday"

# Faraday wrapper for OpenAI chat completions (JSON object responses).
class Email::LlmClient
  def complete_json(system:, user:, temperature: 0)
    response = connection.post("/v1/chat/completions") do |req|
      req.body = {
        model: model,
        temperature: temperature,
        response_format: { type: "json_object" },
        messages: [
          { role: "system", content: system },
          { role: "user", content: user }
        ]
      }
    end
    parse_json!(unwrap!(response, "OpenAI chat"))
  end

  private

  def connection
    @connection ||= Faraday.new(url: "https://api.openai.com") do |f|
      f.request :json
      f.response :json, content_type: /\bjson$/
      f.headers["Authorization"] = "Bearer #{api_key}"
      f.headers["Accept"] = "application/json"
      f.options.timeout = 60
      f.adapter Faraday.default_adapter
    end
  end

  def api_key
    ENV.fetch("OPENAI_API_KEY")
  end

  def model
    ENV.fetch("OPENAI_MODEL", "gpt-4o-mini")
  end

  def unwrap!(response, context)
    unless response.success?
      raise Faraday::Error, "#{context} failed (#{response.status}): #{response.body}"
    end

    response.body
  end

  def parse_json!(body)
    content = body.is_a?(Hash) ? body.dig("choices", 0, "message", "content") : body
    text = content.to_s.sub(/\A```(?:json)?\s*/i, "").sub(/\s*```\z/, "")
    raise Faraday::Error, "OpenAI chat returned empty content" if text.blank?

    JSON.parse(text)
  rescue JSON::ParserError
    raise Faraday::Error, "OpenAI chat returned invalid JSON"
  end
end
