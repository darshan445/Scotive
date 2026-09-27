# frozen_string_literal: true

module Api
  module V1
    module Xero
      class OauthController < Api::V1::BaseController
        skip_before_action :authenticate_user!, only: :callback

        def start
          result = ::Xero::StartOauth.execute(organization: current_organization)
          render_result(result)
        end

        def callback
          result = ::Xero::CompleteOauth.execute(
            code: params[:code],
            state: params[:state],
            error: params[:error],
            error_description: params[:error_description]
          )
          if result.success?
            redirect_to_frontend(xero: "connected")
          else
            redirect_to_frontend(xero: xero_callback_flag(result.errors))
          end
        end

        private

        def xero_callback_flag(errors)
          msg = Array(errors).join(" ")
          return "wrong_scopes" if msg.match?(/wrong apps scopes|invalid_scope|scope/i)
          return "access_denied" if msg.match?(/\baccess_denied\b|user denied|cancelled/i)
          return "state_invalid" if msg.match?(/state|expired/i)

          "error"
        end
      end
    end
  end
end
