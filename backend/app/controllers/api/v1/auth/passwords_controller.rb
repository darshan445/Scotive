# frozen_string_literal: true

module Api
  module V1
    module Auth
      class PasswordsController < Api::V1::BaseController
        skip_before_action :authenticate_user!

        def create
          result = ::Auth::ForgotPassword.execute(email: params[:email])
          render_result(result)
        end

        def update
          result = ::Auth::ResetPassword.execute(
            token: params[:token],
            password: params[:password],
            password_confirmation: params[:password_confirmation]
          )
          render_result(result)
        end
      end
    end
  end
end
