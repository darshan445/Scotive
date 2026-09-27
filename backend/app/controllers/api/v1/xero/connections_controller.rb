# frozen_string_literal: true

module Api
  module V1
    module Xero
      class ConnectionsController < Api::V1::BaseController
        def show
          result = ::Xero::ConnectionStatus.execute(organization: current_organization)
          render_result(result)
        end

        def destroy
          result = ::Xero::Disconnect.execute(organization: current_organization)
          render_result(result)
        end
      end
    end
  end
end
