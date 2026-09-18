# frozen_string_literal: true

module Api
  module V1
    module Gmail
      class ConnectionsController < Api::V1::BaseController
        def show
          result = ::Email::ConnectionStatus.execute(organization: current_organization)
          render_result(result)
        end

        def destroy
          result = ::Email::Disconnect.execute(
            organization: current_organization,
            provider: params[:provider]
          )
          render_result(result)
        end
      end
    end
  end
end
