function init_moderator_comment(old_comment)
{
	var old_comment_repr = '';
	if (old_comment)
	{
		old_comment_repr =
			'<div class="form-row">' +
			 	'<div>' +
					'<label for="id_moderator_old_comment">Previous comment:</label>' +
			 		'<div id="id_moderator_old_comment">' + old_comment + '</div>' +
			 	'</div>' +
			'</div>';
	}

	django.jQuery('#content form .submit-row:last').before(
		'<fieldset class="module aligned">' +
			'<h2>Comments</h2>' +
			old_comment_repr +
			'<div class="form-row">' +
				'<div>' +
					'<label for="id_moderator_new_comment">New comment:</label>' +
					'<textarea id="id_moderator_new_comment" name="moderator_new_comment" rows="5"/>' +
				'</div>' +
			'</div>' +
		'</fieldset>'
	);
}

django.jQuery(function () {
	django.jQuery('tr.object_version_row').click(function () {
		django.jQuery('.object_version_row_selected').removeClass('object_version_row_selected');
		django.jQuery(this).addClass('object_version_row_selected');

		django.jQuery('.object_version_parent_row_selected').removeClass('object_version_parent_row_selected');
		django.jQuery(
			"#"+django.jQuery('.object_version_row_selected').find(".parent_id").val()
		).addClass('object_version_parent_row_selected')

		django.jQuery('.object_version_child_row_selected').removeClass('object_version_child_row_selected');
		django.jQuery('.object_version_row_selected').find(".child_id").each(function(){
			django.jQuery(
				"#"+django.jQuery(this).val()
			).addClass('object_version_child_row_selected');
		});
	});

	django.jQuery(document).keydown(function(e){
	    if (e.keyCode == 40) {
	       django.jQuery('.object_version_row_selected').next().trigger('click');
	       return false;
	    }
	    if (e.keyCode == 38) {
	       django.jQuery('.object_version_row_selected').prev().trigger('click');
	       return false;
	    }
	});

	django.jQuery('input[name=_approve]').click(function () {
		django.jQuery('div#content-main form').submit(function(event) {
			var r = confirm("Are you sure about approving this version?");
			if (r==false){
				django.jQuery(this).unbind('submit');
			}
			return r;
		});
	})

	django.jQuery('input[name=_reject]').click(function () {
		django.jQuery('div#content-main form').submit(function(event) {
			var r = confirm("Are you sure about rejecting this version?");
			if (r==false){
				django.jQuery(this).unbind('submit');
			}
			return r;
		});
	})

	django.jQuery('a.approve-link').click(function (e) {
		var r = confirm("Are you sure about approving this version?");
		if (r == false){
			e.preventDefault();
		}
	})

	django.jQuery('a.reject-link').click(function (e) {
		var r = confirm("Are you sure about rejecting this version?");
		if (r == false){
			e.preventDefault();
		}
	})
});
