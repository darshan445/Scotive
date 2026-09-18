# frozen_string_literal: true

module Api
  module V1
    module Onboarding
      class QboStepsController < Api::V1::BaseController
        def create
          result = ::Onboarding::RecordQboStep.execute(
            organization: current_organization,
            action: params[:action]
          )
          render_result(result)
        end
      end
    end
  end
end
