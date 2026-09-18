# frozen_string_literal: true

module Api
  module Admin
    class BaseController < Api::V1::BaseController
      skip_before_action :authenticate_user!
      before_action :require_admin!

      private

      def require_admin!
        return if session[:admin_email].present?

        render json: {
          errors: [ { status: "401", code: "unauthorized", detail: "Admin sign-in required" } ]
        }, status: :unauthorized
      end
    end
  end
end
