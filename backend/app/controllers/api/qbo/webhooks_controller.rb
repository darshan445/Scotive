# frozen_string_literal: true

module Api
  module Qbo
    class WebhooksController < ApplicationController
      def create
        result = ::Webhooks::Ingest.execute(
          provider: "qbo",
          raw_body: request.raw_post,
          signature: request.get_header("HTTP_INTUIT_SIGNATURE").to_s
        )
        render_webhook_result(result)
      end

      private

      def render_webhook_result(result)
        if result.success?
          head :ok
        else
          detail = Array(result.errors).join(" ")
          status = detail.match?(/signature|not configured/i) ? :unauthorized : :bad_request
          render json: {
            errors: [ { status: Rack::Utils.status_code(status).to_s, code: status.to_s, detail: detail } ]
          }, status: status
        end
      end
    end
  end
end
