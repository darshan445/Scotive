# frozen_string_literal: true

module Api
  module V1
    module Onboarding
      class StatesController < Api::V1::BaseController
        def show
          result = ::Onboarding::BuildState.execute(organization: current_organization)
          render_result(result)
        end
      end
    end
  end
end
