# frozen_string_literal: true

module Api
  module V1
    class BaseController < ApplicationController
      prepend_before_action :skip_devise_trackable
      before_action :authenticate_user!

      private

      # JWT auth runs on every API call. Do not treat those as new Devise sign-ins.
      def skip_devise_trackable
        request.env["devise.skip_trackable"] = true
      end

      def bearer_token
        request.headers["Authorization"].to_s
      end

      def render_result(result, status: :ok, failure_status: :unprocessable_content)
        if result.success?
          render json: { data: result.data }, status: status
        else
          http_status = Rack::Utils.status_code(failure_status)
          render json: { errors: normalize_errors(result.errors, http_status, failure_status) },
                 status: failure_status
        end
      end

      def normalize_errors(errors, http_status, code)
        details = Array(errors).flat_map { |error| error.to_s.split(/,\s*/) }.compact_blank
        details = [ "Request failed" ] if details.empty?

        details.map do |detail|
          { status: http_status.to_s, code: code.to_s, detail: detail }
        end
      end
    end
  end
end
