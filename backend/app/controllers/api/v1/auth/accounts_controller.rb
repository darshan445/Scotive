# frozen_string_literal: true

module Api
  module V1
    module Auth
      class AccountsController < Api::V1::BaseController
        def destroy
          result = ::Auth::DeleteAccount.execute(
            user: current_user,
            confirm_email: params[:confirm_email],
            token: bearer_token
          )
          render_result(result)
        end
      end
    end
  end
end
