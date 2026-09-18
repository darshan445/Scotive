# frozen_string_literal: true

module Api
  module V1
    module Auth
      class SessionsController < Api::V1::BaseController
        skip_before_action :authenticate_user!, only: :create

        def create
          result = ::Auth::SignIn.execute(
            email: params[:email],
            password: params[:password],
            request: request
          )
          render_result(result, failure_status: :unauthorized)
        end

        def destroy
          result = ::Auth::SignOut.execute(token: bearer_token, user: current_user)
          if result.success?
            head :no_content
          else
            render_result(result, failure_status: :unauthorized)
          end
        end
      end
    end
  end
end
