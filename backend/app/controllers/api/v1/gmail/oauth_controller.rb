# frozen_string_literal: true

module Api
  module V1
    module Gmail
      class OauthController < Api::V1::BaseController
        skip_before_action :authenticate_user!, only: :callback

        def start
          result = ::Email::StartOauth.execute(
            organization: current_organization,
            provider: params[:provider]
          )
          render_result(result)
        end

        def callback
          result = ::Email::CompleteOauth.execute(
            account_id: params[:account_id].presence || params[:accountId],
            state: params[:state]
          )
          if result.success?
            provider = result.data[:provider] == "outlook" ? "outlook" : "google"
            redirect_to_frontend(mail: "connected", provider: provider)
          else
            redirect_to_frontend(mail: mail_callback_flag(result.errors), provider: params[:provider])
          end
        end

        private

        def mail_callback_flag(errors)
          msg = Array(errors).join(" ")
          return "access_denied" if msg.match?(/denied|cancelled/i)
          return "state_invalid" if msg.match?(/state|expired/i)

          "error"
        end
      end
    end
  end
end
