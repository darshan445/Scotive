# frozen_string_literal: true

module Api
  module V1
    module Auth
      class RegistrationsController < Api::V1::BaseController
        skip_before_action :authenticate_user!

        def create
          result = ::Auth::SignUp.execute(
            email: params[:email],
            password: params[:password],
            name: params[:name],
            timezone: params[:timezone]
          )
          render_result(result, status: :created)
        end
      end
    end
  end
end
