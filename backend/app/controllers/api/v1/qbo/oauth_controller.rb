# frozen_string_literal: true

module Api
  module V1
    module Qbo
      class OauthController < Api::V1::BaseController
        skip_before_action :authenticate_user!, only: :callback

        def start
          result = ::Quickbooks::StartOauth.execute(organization: current_organization)
          render_result(result)
        end

        def callback
          result = ::Quickbooks::CompleteOauth.execute(
            code: params[:code],
            realm_id: params[:realmId].presence || params[:realm_id],
            state: params[:state],
            error: params[:error]
          )
          if result.success?
            redirect_to_frontend(qbo: "connected")
          else
            redirect_to_frontend(qbo: qbo_callback_flag(result.errors))
          end
        end

        private

        def qbo_callback_flag(errors)
          msg = Array(errors).join(" ")
          return "access_denied" if msg.match?(/denied|cancelled/i)
          return "state_invalid" if msg.match?(/state|expired/i)

          "error"
        end
      end
    end
  end
end
