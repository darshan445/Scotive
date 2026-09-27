# frozen_string_literal: true

module Api
  module Xero
    class WebhooksController < ApplicationController
      def create
        result = ::Webhooks::Ingest.execute(
          provider: "xero",
          raw_body: request.raw_post,
          signature: request.get_header("HTTP_X_XERO_SIGNATURE").to_s
        )
        if result.success?
          head :ok
        else
          head :unauthorized
        end
      end
    end
  end
end
