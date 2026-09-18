# frozen_string_literal: true

module Api
  module V1
    module Auth
      class MeController < Api::V1::BaseController
        def show
          result = ::Auth::SessionPayload.execute(user: current_user)
          render_result(result)
        end
      end
    end
  end
end
